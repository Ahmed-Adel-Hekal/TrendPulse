"""routes/strategy.py — AI content strategy generation."""
from __future__ import annotations
import json
import datetime
from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import get_current_user, escape_html, escape_js
from db import (create_strategy, update_strategy, get_strategy, get_user_strategies,
                add_calendar_items, get_brands, get_user_settings, quota_ok_atomic,
                detect_niche, LANGUAGE_CHOICES)
from core.i18n import normalize_lang, t as _t
import ui
import pipelines

router = APIRouter()


def _get_lang(user):
    s = get_user_settings(user["id"])
    return normalize_lang(s.get("ui_language","en"))


# ── Strategy list ──────────────────────────────────────────────────────────────
@router.get("/strategy", response_class=HTMLResponse)
async def strategy_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    lang       = _get_lang(user)
    strategies = get_user_strategies(user["id"])
    brands     = get_brands(user["id"])

    brand_opts = "".join(
        f'<option value="{escape_html(b["id"])}">{escape_html(b["name"])}</option>'
        for b in brands
    ) or '<option value="">— No brands yet —</option>'

    lang_opts = "".join(
        f'<option value="{l}">{l}</option>' for l in LANGUAGE_CHOICES
    )

    dur_opts = "".join(
        f'<option value="{d}">{d} days</option>'
        for d in [7,14,30,60,90]
    )

    sb = {"generating":"badge-amber","draft":"badge-gray","approved":"badge-green","failed":"badge-red"}
    strat_rows = "".join(
        f'<tr>'
        f'<td style="font-weight:600;">{escape_html(s["title"][:60])}</td>'
        f'<td style="font-family:var(--mono);font-size:10px;">{s["duration_days"]}d</td>'
        f'<td><span class="badge {sb.get(s["status"],"badge-gray")}">{s["status"]}</span></td>'
        f'<td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{s["created_at"][:10]}</td>'
        f'<td><a class="btn btn-ghost btn-sm" href="/strategy/{s["id"]}">View</a></td>'
        f'</tr>'
        for s in strategies
    ) or f'<tr><td colspan="5" style="text-align:center;color:var(--text3);padding:24px;">No strategies yet</td></tr>'

    content = f"""
    <div class="topbar">
      <div><div class="topbar-title">{_t(lang,"nav.strategy")}</div></div>
      <button class="btn btn-primary" onclick="document.getElementById('new-strat-modal').style.display='flex'">+ New Strategy</button>
    </div>
    <div class="content">
      <div class="table-wrap">
        <table><thead><tr><th>Title</th><th>Duration</th><th>Status</th><th>Created</th><th></th></tr></thead>
        <tbody>{strat_rows}</tbody></table>
      </div>
    </div>

    <div id="new-strat-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:200;align-items:center;justify-content:center;">
      <div class="card" style="width:100%;max-width:500px;max-height:90vh;overflow-y:auto;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
          <div class="card-title" style="margin:0;">New Content Strategy</div>
          <button style="background:none;border:none;color:var(--text3);font-size:18px;cursor:pointer;" onclick="document.getElementById('new-strat-modal').style.display='none'">✕</button>
        </div>
        <form method="post" action="/strategy/create">
          <div class="form-group">
            <label class="form-label">Topic / Brand</label>
            <input class="form-input" name="topic" placeholder="e.g. AI SaaS, fitness brand, restaurant chain" required/>
          </div>
          <div class="form-group">
            <label class="form-label">Duration</label>
            <select class="form-select" name="duration_days">{dur_opts}</select>
          </div>
          <div class="form-group">
            <label class="form-label">Language</label>
            <select class="form-select" name="language">{lang_opts}</select>
          </div>
          <div class="form-group">
            <label class="form-label">Brand <span style="color:var(--text3);font-weight:400;">(optional)</span></label>
            <select class="form-select" name="brand_id"><option value="">No brand</option>{brand_opts}</select>
          </div>
          <div style="display:flex;gap:10px;">
            <button class="btn btn-primary" type="submit">Generate Strategy →</button>
            <button class="btn btn-ghost" type="button" onclick="document.getElementById('new-strat-modal').style.display='none'">Cancel</button>
          </div>
        </form>
      </div>
    </div>"""
    return HTMLResponse(ui._page(content, user, "Strategy", "strategy", lang))


# ── Create strategy (background) ───────────────────────────────────────────────
@router.post("/strategy/create")
async def strategy_create(request: Request, background_tasks: BackgroundTasks,
                           topic: str = Form(""), duration_days: int = Form(30),
                           language: str = Form("English"), brand_id: str = Form("")):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    topic = topic.strip()
    if not topic:
        return RedirectResponse("/strategy", status_code=303)

    settings  = get_user_settings(user["id"])
    title     = f"{topic[:40]} — {duration_days}d Plan"
    sid       = create_strategy(user["id"], brand_id or None, title, topic, duration_days)

    cfg = {
        "topic":        topic,
        "duration_days":duration_days,
        "language":     language,
        "brand_id":     brand_id,
        "llm_api_key":  settings.get("gemini_key",""),
        "llm_provider": settings.get("llm_provider","google"),
        "llm_model":    settings.get("llm_model","gemini-2.5-flash"),
    }
    background_tasks.add_task(_run_strategy_pipeline, sid, user["id"], cfg)
    return RedirectResponse(f"/strategy/{sid}", status_code=303)


def _run_strategy_pipeline(sid: str, uid: str, cfg: dict):
    """Generate a full content strategy and seed calendar items."""
    import logging, os
    logger = logging.getLogger("Strategy")
    try:
        update_strategy(sid, "generating")

        from core.gemini_client import Agent
        api_key  = cfg.get("llm_api_key","") or os.getenv("GEMINI_API_KEY","")
        provider = cfg.get("llm_provider","google")
        model    = cfg.get("llm_model","gemini-2.5-flash")
        duration = cfg.get("duration_days",30)
        topic    = cfg.get("topic","")
        language = cfg.get("language","English")

        agent = Agent(provider=provider, model=model, api_key=api_key)

        prompt = f"""Create a {duration}-day content marketing strategy for: {topic}
Language: {language}

Generate a JSON array of {duration} daily content plans (one per day).
Each item must have:
- "day": integer (1 to {duration})
- "date": ISO date string (starting from today)
- "platform": one of Instagram/TikTok/LinkedIn/Twitter/Facebook
- "content_type": "static" or "video"
- "title": short post title (max 60 chars)
- "hook": compelling opening line
- "angle": content angle / narrative
- "trend_tie_in": relevant trend or hashtag to leverage
- "competitor_angle": what competitors are NOT doing that you will
- "visual_direction": brief visual description
- "hashtags": list of 5-8 hashtags

Return ONLY valid JSON array, no markdown, no preamble."""

        raw  = agent.generate(prompt, max_tokens=8000)
        plan = _parse_strategy_json(raw, duration, topic)

        update_strategy(sid, "approved", plan={"days": plan})

        # Seed calendar items
        base_date = datetime.date.today()
        cal_items = []
        for item in plan:
            day_offset  = item.get("day",1) - 1
            pub_date    = (base_date + datetime.timedelta(days=day_offset)).isoformat()
            cal_items.append({
                "strategy_id":  sid,
                "title":        item.get("title",""),
                "platform":     item.get("platform","Instagram"),
                "content_type": item.get("content_type","static"),
                "publish_date": pub_date,
                "publish_time": "09:00",
                "status":       "scheduled",
                "idea":         item,
            })
        if cal_items:
            add_calendar_items(uid, cal_items)

        logger.info("Strategy %s done — %d days generated, %d calendar items", sid, len(plan), len(cal_items))

    except Exception as e:
        logger.error("Strategy %s failed: %s", sid, e)
        update_strategy(sid, "failed")


def _parse_strategy_json(raw: str, duration: int, topic: str):
    """Parse LLM strategy JSON with fallback."""
    import re
    m = re.search(r'\[[\s\S]*\]', raw)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # Fallback: generate basic plan
    base  = datetime.date.today()
    plats = ["Instagram","TikTok","LinkedIn","Twitter/X","Facebook"]
    types = ["static","video"]
    return [
        {
            "day":        i+1,
            "date":       (base + datetime.timedelta(days=i)).isoformat(),
            "platform":   plats[i % len(plats)],
            "content_type": types[i % 2],
            "title":      f"Day {i+1}: {topic} — Content Idea",
            "hook":       f"Day {i+1} content for {topic}",
            "angle":      "Educational / engagement",
            "trend_tie_in":    "",
            "competitor_angle": "",
            "visual_direction": "Clean, branded",
            "hashtags":   [f"#{topic.replace(' ','')}", "#content", "#marketing"],
        }
        for i in range(duration)
    ]


# ── Strategy detail ────────────────────────────────────────────────────────────
@router.get("/strategy/{sid}", response_class=HTMLResponse)
async def strategy_detail(request: Request, sid: str):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    lang = _get_lang(user)
    strat = get_strategy(sid, user["id"])
    if not strat: return RedirectResponse("/strategy", status_code=303)

    status = strat["status"]

    if status == "generating":
        content = f"""
        <div class="topbar"><div><div class="topbar-title">Generating Strategy…</div></div></div>
        <div class="content" style="display:flex;align-items:center;justify-content:center;min-height:60vh;">
          <div style="text-align:center;">
            <div class="spinner" style="width:48px;height:48px;border-width:3px;margin:0 auto 24px;"></div>
            <div style="font-size:15px;font-weight:600;">AI is building your {strat['duration_days']}-day strategy…</div>
          </div>
        </div>
        <script>setTimeout(()=>location.replace(location.href),3000);</script>"""
        return HTMLResponse(ui._page(content, user, "Strategy…", "strategy", lang))

    if status == "failed":
        content = f"""
        <div class="topbar"><div><div class="topbar-title">Strategy Failed</div></div>
          <a class="btn btn-ghost" href="/strategy">← Back</a></div>
        <div class="content"><div class="alert alert-danger">Strategy generation failed. Please try again.</div></div>"""
        return HTMLResponse(ui._page(content, user, "Failed", "strategy", lang))

    plan = strat.get("plan",{}) or {}
    days = plan.get("days",[])

    plat_icons = {"Instagram":"📸","TikTok":"🎬","LinkedIn":"💼","Twitter/X":"🐦","Facebook":"👥"}
    type_badge = {"static":"badge-blue","video":"badge-purple"}

    day_rows = "".join(
        f'<tr>'
        f'<td style="font-family:var(--mono);font-size:11px;color:var(--text3);">Day {d.get("day",i+1)}</td>'
        f'<td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{d.get("date","")}</td>'
        f'<td>{plat_icons.get(d.get("platform",""),"📱")} {escape_html(d.get("platform",""))}</td>'
        f'<td><span class="badge {type_badge.get(d.get("content_type","static"),"badge-gray")}">{d.get("content_type","static")}</span></td>'
        f'<td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{escape_html(d.get("title","")[:80])}</td>'
        f'<td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text2);font-size:12px;">{escape_html(d.get("hook","")[:80])}</td>'
        f'</tr>'
        for i,d in enumerate(days[:100])
    ) or '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text3);">No days generated</td></tr>'

    content = f"""
    <div class="topbar">
      <div>
        <div class="topbar-title">{escape_html(strat["title"])}</div>
        <div class="topbar-sub">{len(days)} days · {strat.get("topic","")[:40]}</div>
      </div>
      <div class="flex gap-2">
        <a class="btn btn-ghost" href="/strategy">← Back</a>
        <a class="btn btn-ghost btn-sm" href="/calendar">📅 Calendar</a>
      </div>
    </div>
    <div class="content">
      <div class="table-wrap">
        <table>
          <thead><tr><th>Day</th><th>Date</th><th>Platform</th><th>Type</th><th>Title</th><th>Hook</th></tr></thead>
          <tbody>{day_rows}</tbody>
        </table>
      </div>
    </div>"""
    return HTMLResponse(ui._page(content, user, strat["title"][:40], "strategy", lang))
