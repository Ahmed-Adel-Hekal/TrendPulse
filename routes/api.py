"""routes/api.py — JSON API endpoints for idea management, regeneration, approval."""
from __future__ import annotations
import json
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from auth import get_current_user
from db import (get_generation, update_generation, get_conn, safe_json_loads,
                quota_ok_atomic)
import pipelines

router = APIRouter()


def _get_user_gen(request, gid):
    user = get_current_user(request)
    if not user:
        return None, None, JSONResponse({"error":"Unauthorized"}, status_code=401)
    gen = get_generation(gid, user["id"])
    if not gen:
        return None, None, JSONResponse({"error":"Not found"}, status_code=404)
    return user, gen, None


# ── Update idea (save edits) ───────────────────────────────────────────────────
@router.post("/api/update-idea/{gid}/{idx}")
async def update_idea(request: Request, gid: str, idx: int):
    user, gen, err = _get_user_gen(request, gid)
    if err: return err

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error":"Invalid JSON"}, status_code=400)

    result = gen.get("result") or {}
    ideas  = result.get("ideas", [])
    if idx < 0 or idx >= len(ideas):
        return JSONResponse({"error":"Idea index out of range"}, status_code=400)

    idea = ideas[idx]
    for field in ("hook","post_copy","caption","image_description","cta"):
        if field in body:
            idea[field] = body[field]
    if "script" in body and body["script"]:
        idea["script"] = body["script"]
    if "hashtags" in body:
        idea["hashtags"] = body["hashtags"]

    ideas[idx]       = idea
    result["ideas"]  = ideas
    update_generation(gid, gen["status"], result=result)
    return JSONResponse({"ok": True})


# ── Regenerate single idea ─────────────────────────────────────────────────────
@router.post("/api/regenerate-idea/{gid}/{idx}")
async def regenerate_idea(request: Request, gid: str, idx: int,
                           background_tasks: BackgroundTasks = None):
    user, gen, err = _get_user_gen(request, gid)
    if err: return err

    if not quota_ok_atomic(user):
        return JSONResponse({"error":"Quota exceeded — upgrade your plan"}, status_code=429)

    cfg = gen.get("config", {}) or {}
    cfg["regenerate_idx"] = idx

    new_gid = None
    try:
        from db import create_generation, detect_niche
        new_gid = create_generation(
            user["id"], cfg.get("topic",""), cfg.get("content_type","static"),
            cfg.get("platforms",[]), cfg.get("language","English"), cfg
        )
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_in_executor(pipelines._pipeline_pool, pipelines._run_pipeline,
                             new_gid, user["id"], cfg)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"ok": True, "new_gid": new_gid})


# ── Approve single idea (generate media) ──────────────────────────────────────
@router.post("/api/approve-idea/{gid}/{idx}")
async def approve_idea(request: Request, gid: str, idx: int):
    user, gen, err = _get_user_gen(request, gid)
    if err: return err

    result = gen.get("result") or {}
    ideas  = result.get("ideas", [])
    if idx < 0 or idx >= len(ideas):
        return JSONResponse({"error":"Idea index out of range"}, status_code=400)

    cfg = gen.get("config", {}) or {}

    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        pipelines._pipeline_pool,
        pipelines._run_single_idea_media,
        gid, user["id"], idx, {"ideas": [ideas[idx]]}, cfg
    )
    return JSONResponse({"ok": True, "status": "generating"})


# ── Poll idea status ───────────────────────────────────────────────────────────
@router.get("/api/idea-status/{gid}/{idx}")
async def idea_status(request: Request, gid: str, idx: int):
    user, gen, err = _get_user_gen(request, gid)
    if err: return err

    result  = gen.get("result") or {}
    media_by_idx = {
        int(r.get("idea_index", -1)): r
        for r in result.get("results", [])
        if isinstance(r, dict) and r.get("idea_index") is not None
    }
    media = media_by_idx.get(idx, {})
    return JSONResponse({
        "status":    media.get("status", gen.get("status","pending")),
        "has_media": bool(media.get("image_path") or media.get("video_path")),
    })


# ── Generation status poll ─────────────────────────────────────────────────────
@router.get("/api/generation-status/{gid}")
async def generation_status(request: Request, gid: str):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error":"Unauthorized"}, status_code=401)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, error FROM generations WHERE id=? AND user_id=?",
            (gid, user["id"])
        ).fetchone()
    if not row:
        return JSONResponse({"error":"Not found"}, status_code=404)
    return JSONResponse({"status": row["status"], "error": row["error"] or ""})


# ── Stats endpoint (admin-gated) ───────────────────────────────────────────────
@router.get("/admin/stats")
async def admin_stats(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error":"Unauthorized"}, status_code=401)
    if not user.get("is_admin"):
        return JSONResponse({"error":"Admin access required"}, status_code=403)

    from db import get_system_stats
    return JSONResponse(get_system_stats())


# ── Cancel generation ──────────────────────────────────────────────────────────
@router.post("/api/cancel-generation/{gid}")
async def cancel_generation(request: Request, gid: str):
    user, gen, err = _get_user_gen(request, gid)
    if err: return err

    if gen["status"] not in ("pending","scheduled","running"):
        return JSONResponse({"error":"Cannot cancel in current state"}, status_code=400)

    with get_conn() as conn:
        conn.execute("UPDATE generations SET status='cancelled' WHERE id=? AND user_id=?",
                     (gid, user["id"]))
    return JSONResponse({"ok": True})
