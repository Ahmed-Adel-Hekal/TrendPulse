"""pipelines.py — Background pipeline runners and scheduler. (v4 — improved)"""
from __future__ import annotations
import asyncio as _asyncio
import logging
from concurrent.futures import ThreadPoolExecutor as _TPE
from pathlib import Path

from db import (get_conn, get_generation, update_generation,
                quota_ok_atomic, safe_json_loads, OUTPUT_ROOT)

logger = logging.getLogger("TrendPulse.pipeline")

# Separate pools: pipeline workers vs scheduler (prevents starvation)
_pipeline_pool  = _TPE(max_workers=4, thread_name_prefix="pipeline")
_scheduler_pool = _TPE(max_workers=2, thread_name_prefix="scheduler")
_bulk_progress: dict = {}

from db import _sanitise_for_json  # noqa: F401


# ── Core pipeline ──────────────────────────────────────────────────────────────
def _run_pipeline(gid: str, uid: str, cfg: dict):
    import time as _t
    t0 = _t.perf_counter()

    # Skip if cancelled before firing
    with get_conn() as conn:
        row = conn.execute("SELECT status FROM generations WHERE id=?", (gid,)).fetchone()
    if row and row["status"] == "cancelled":
        logger.info("Pipeline skipped — gid=%s cancelled", gid)
        return

    # NOTE: record_usage() is NO LONGER called here.
    # It is called inside update_generation() when status → "completed".
    update_generation(gid, "running")
    logger.info(
        "Pipeline START gid=%s topic=%r provider=%s model=%s ideas=%s type=%s",
        gid, cfg.get("topic","")[:40], cfg.get("llm_provider","google"),
        cfg.get("llm_model","?"), cfg.get("number_idea",1), cfg.get("content_type","static")
    )

    try:
        from core.orchestrator import Orchestrator
        result = Orchestrator().run(
            topic            = cfg["topic"],
            platforms        = cfg["platforms"],
            content_type     = cfg["content_type"],
            language         = cfg["language"],
            brand_color      = [cfg["brand_color"]],
            number_idea      = cfg["number_idea"],
            niche            = cfg["niche"],
            output_dir       = str(OUTPUT_ROOT / uid / gid),
            image_url        = cfg.get("image_url",""),
            aspect_ratio     = cfg.get("aspect_ratio","9:16"),
            competitor_urls  = cfg.get("competitor_urls",[]) or [],
            product_features = cfg.get("product_features",[]) or [],
            brand_profile    = cfg.get("brand_profile",{}) or {},
            llm_provider     = cfg.get("llm_provider","google"),
            llm_model        = cfg.get("llm_model","gemini-2.5-flash"),
            image_model      = cfg.get("image_model","gemini-3.1-flash-image-preview"),
            video_model      = cfg.get("video_model","google/veo-3.1-i2v"),
            llm_api_key      = cfg.get("llm_api_key") or None,
            image_api_key    = cfg.get("image_api_key") or None,
            video_api_key    = cfg.get("video_api_key") or None,
            human_review     = cfg.get("human_review", False),
        )

        status       = result.get("status", "completed")
        fallback_used= bool(result.get("fallback_used", False))

        update_generation(gid, status, result=result, fallback_used=fallback_used)
        logger.info(
            "Pipeline DONE gid=%s status=%s fallback=%s elapsed=%.2fs",
            gid, status, fallback_used, _t.perf_counter() - t0
        )

    except Exception as exc:
        logger.error("Generation %s failed: %s", gid, exc)
        update_generation(gid, "failed", error=str(exc))


# ── Media approval helpers ─────────────────────────────────────────────────────
def _run_media_approval(gid: str, uid: str, cfg: dict, ideas_json: dict):
    update_generation(gid, "generating_media")
    try:
        from agents.content_agent import run_media_generation
        out_dir = str(OUTPUT_ROOT / uid / gid)
        media   = run_media_generation(
            parsed       = ideas_json,
            content_type = cfg["content_type"],
            language     = cfg["language"],
            brand_color  = [cfg["brand_color"]],
            image_url    = cfg.get("image_url",""),
            aspect_ratio = cfg.get("aspect_ratio","9:16"),
            out_dir      = out_dir,
            image_model  = cfg.get("image_model","gemini-3.1-flash-image-preview"),
            video_model  = cfg.get("video_model","google/veo-3.1-i2v"),
            llm_api_key  = cfg.get("llm_api_key") or None,
            image_api_key= cfg.get("image_api_key") or None,
            video_api_key= cfg.get("video_api_key") or None,
        )
        gen = get_generation(gid, uid)
        if gen and gen.get("result"):
            merged = gen["result"]
            merged["results"] = media["results"]
            merged["status"]  = "completed"
            if media.get("warnings"):
                merged["warning"] = " | ".join(media["warnings"])
            update_generation(gid, "completed", result=merged)
    except Exception as exc:
        logger.error("Media approval failed for %s: %s", gid, exc)
        update_generation(gid, "failed", error=str(exc))


def _run_single_idea_media(gid: str, uid: str, idea_idx: int,
                            single_idea_json: dict, cfg: dict):
    try:
        from agents.content_agent import run_media_generation
        out_dir = str(OUTPUT_ROOT / uid / gid)
        media   = run_media_generation(
            parsed       = single_idea_json,
            content_type = cfg.get("content_type","static"),
            language     = cfg.get("language","English"),
            brand_color  = [cfg.get("brand_color","#4f8ef7")],
            image_url    = cfg.get("image_url",""),
            aspect_ratio = cfg.get("aspect_ratio","9:16"),
            out_dir      = out_dir,
            image_model  = cfg.get("image_model","gemini-3.1-flash-image-preview"),
            video_model  = cfg.get("video_model","google/veo-3.1-i2v"),
            llm_api_key  = cfg.get("llm_api_key") or None,
            image_api_key= cfg.get("image_api_key") or None,
            video_api_key= cfg.get("video_api_key") or None,
        )
        gen = get_generation(gid, uid)
        if gen and gen.get("result"):
            result   = gen["result"]
            existing = result.get("results", [])
            existing = [r for r in existing
                        if not (isinstance(r, dict) and r.get("idea_index") == idea_idx)]
            for r in media.get("results", []):
                if isinstance(r, dict):
                    r["idea_index"] = idea_idx
                    existing.append(r)
            result["results"] = existing
            update_generation(gid, "completed", result=result)
    except Exception as e:
        logger.error("Single idea media failed: %s", e)


# ── Bulk strategy runner ───────────────────────────────────────────────────────
def _run_strategy_post(gid: str, uid: str, cfg: dict, sid: str, day_idx: int, total: int):
    _bulk_progress.setdefault(sid, {"total": total, "done": 0, "failed": 0, "gids": {}})
    _bulk_progress[sid]["gids"][day_idx] = {"gid": gid, "status": "running"}
    _run_pipeline(gid, uid, cfg)
    gen    = get_generation(gid, uid)
    status = gen["status"] if gen else "failed"
    _bulk_progress[sid]["gids"][day_idx]["status"] = status
    if status == "completed":
        _bulk_progress[sid]["done"] += 1
    else:
        _bulk_progress[sid]["failed"] += 1


# ── Background scheduler ───────────────────────────────────────────────────────
async def _scheduler_loop():
    """Check every 60s for scheduled generations whose time has arrived."""
    await _asyncio.sleep(5)
    while True:
        try:
            _fire_due_generations()
        except Exception as exc:
            logger.error("Scheduler error: %s", exc)
        await _asyncio.sleep(60)


def _fire_due_generations():
    with get_conn() as conn:
        due = conn.execute(
            """SELECT id, user_id, config_json FROM generations
               WHERE status = 'scheduled'
                 AND scheduled_at IS NOT NULL
                 AND scheduled_at <= datetime('now')
               ORDER BY scheduled_at ASC LIMIT 20"""
        ).fetchall()
    if not due:
        return

    logger.info("Scheduler: firing %d due generation(s)", len(due))
    for row in due:
        gid = row["id"]; uid = row["user_id"]
        cfg = safe_json_loads(row["config_json"], {})
        # Get user for quota check
        from db import get_user_by_id
        user = get_user_by_id(uid)
        if not user or not quota_ok_atomic(user):
            logger.warning("Scheduler: skipping gid=%s — quota exhausted", gid)
            with get_conn() as conn:
                conn.execute(
                    "UPDATE generations SET status='failed', error='Quota exhausted' WHERE id=?",
                    (gid,)
                )
            continue
        with get_conn() as conn:
            conn.execute("UPDATE generations SET status='pending' WHERE id=?", (gid,))
        _scheduler_pool.submit(_run_pipeline, gid, uid, cfg)
