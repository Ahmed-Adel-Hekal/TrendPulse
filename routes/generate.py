"""routes/generate.py — Generate page, result page, history."""
from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import get_current_user, escape_html, escape_js
from db import (create_generation, get_generation, get_user_generations,
                quota_ok_atomic, get_user_settings, get_default_brand,
                PLATFORM_CHOICES, LANGUAGE_CHOICES, detect_niche, get_brand_profile)
from core.i18n import normalize_lang, t as _t
import ui
import pipelines

router = APIRouter()

STATUS_BADGE = {
    "completed":         "badge-green",
    "running":           "badge-amber",
    "failed":            "badge-red",
    "pending":           "badge-gray",
    "scheduled":         "badge-blue",
    "awaiting_approval": "badge-amber",
    "cancelled":         "badge-gray",
    "generating_media":  "badge-amber",
}


def _get_lang_and_settings(user):
    s    = get_user_settings(user["id"])
    lang = normalize_lang(s.get("ui_language", "en"))
    return lang, s


def _platform_checkboxes(prefill_plat=""):
    parts = []
    for p in PLATFORM_CHOICES:
        if prefill_plat:
            chk = "checked" if p == prefill_plat else ""
        else:
            chk = "checked" if p in ("Instagram", "TikTok") else ""
        parts.append(
            '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;">'
            '<input type="checkbox" name="platforms" value="' + escape_html(p) + '" ' + chk +
            ' style="accent-color:var(--accent);width:15px;height:15px;"/>' +
            escape_html(p) + "</label>"
        )
    return "".join(parts)


def _lang_options(selected="English"):
    parts = []
    for lc in LANGUAGE_CHOICES:
        sel = "selected" if lc == selected else ""
        parts.append(
            '<option value="' + escape_html(lc) + '" ' + sel + ">" + escape_html(lc) + "</option>"
        )
    return "".join(parts)


# ── Generate form ──────────────────────────────────────────────────────────────
@router.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request, msg: str = "",
                        topic: str = "", platform: str = "",
                        content_type: str = "", from_calendar: str = "",
                        cal_id: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    lang, _ = _get_lang_and_settings(user)
    brand   = get_default_brand(user["id"])
    bc      = brand["profile"].get("brand_color", "#4f8ef7") if brand else "#4f8ef7"
    bv      = brand["profile"].get("brand_voice", "")        if brand else ""

    prefill_topic = topic.strip()
    prefill_ct    = content_type if content_type in ("static","video") else "static"
    prefill_plat  = platform.strip()

    from_cal_banner = ""
    if from_calendar and prefill_topic:
        from_cal_banner = (
            '<div class="alert alert-info mb-3" style="font-size:13px;">'
            '📅 Pre-filled from your content calendar. Review and click Generate.'
            "</div>"
        )

    msg_html = ""
    if msg:
        msg_html = '<div class="alert alert-success mb-3">' + escape_html(msg) + "</div>"

    content = (
        '<div class="topbar"><div>'
        '<div class="topbar-title">' + escape_html(_t(lang, "gen.title")) + "</div>"
        "</div></div>"
        '<div class="content">'
        + from_cal_banner + msg_html +
        '<form method="post" action="/generate" id="gen-form">'
        '<div class="grid-2" style="gap:20px;align-items:start;">'

        # ---- Left column ----
        "<div>"
        '<div class="card mb-4">'
        '<div class="card-title">Content</div>'
        '<div class="form-group">'
        '<label class="form-label">' + escape_html(_t(lang, "gen.topic")) + " *</label>"
        '<input class="form-input" name="topic" value="' + escape_html(prefill_topic) + '" placeholder="e.g. AI product launch, fitness app..." required/>'
        "</div>"
        '<div class="form-group">'
        '<label class="form-label">' + escape_html(_t(lang, "gen.features")) + "</label>"
        '<textarea class="form-textarea" name="product_features" style="min-height:70px;" placeholder="Key features (one per line)..."></textarea>'
        "</div>"
        '<div class="form-group">'
        '<label class="form-label">' + escape_html(_t(lang, "gen.competitor_urls")) + "</label>"
        '<textarea class="form-textarea" name="competitor_urls" style="min-height:60px;" placeholder="https://instagram.com/competitor"></textarea>'
        '<div class="form-hint">Add competitor social URLs for intelligence analysis</div>'
        "</div>"
        "</div>"

        '<div class="card">'
        '<div class="card-title">Strategy</div>'
        '<div class="form-group">'
        '<label class="form-label">' + escape_html(_t(lang, "gen.type_static")) + " / " + escape_html(_t(lang, "gen.type_video")) + "</label>"
        '<div style="display:flex;gap:10px;">'
        '<label style="flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:10px;border:1px solid var(--accent);border-radius:var(--r2);cursor:pointer;font-size:13px;" id="lbl-static">'
        '<input type="radio" name="content_type" value="static" ' + ('checked' if prefill_ct != 'video' else '') + ' style="accent-color:var(--accent);"/> Static Post'
        "</label>"
        '<label style="flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:10px;border:1px solid var(--border);border-radius:var(--r2);cursor:pointer;font-size:13px;" id="lbl-video">'
        '<input type="radio" name="content_type" value="video" ' + ('checked' if prefill_ct == 'video' else '') + ' style="accent-color:var(--accent);"/> Video'
        "</label>"
        "</div>"
        "</div>"
        '<div class="form-group">'
        '<label class="form-label">' + escape_html(_t(lang, "gen.ideas")) + "</label>"
        '<select class="form-select" name="number_idea">'
        '<option value="1">1 idea</option>'
        '<option value="2">2 ideas</option>'
        '<option value="3" selected>3 ideas</option>'
        '<option value="5">5 ideas</option>'
        "</select>"
        "</div>"
        '<div class="form-group">'
        '<label class="form-label">' + escape_html(_t(lang, "gen.language")) + "</label>"
        '<select class="form-select" name="language">' + _lang_options() + "</select>"
        "</div>"
        "</div>"
        "</div>"  # end left col

        # ---- Right column ----
        "<div>"
        '<div class="card mb-4">'
        '<div class="card-title">Platforms</div>'
        '<div style="display:flex;flex-direction:column;gap:8px;">'
        + _platform_checkboxes(prefill_plat) +
        "</div></div>"

        '<div class="card mb-4">'
        '<div class="card-title">Brand</div>'
        '<div class="form-group">'
        '<label class="form-label">Brand Color</label>'
        '<div style="display:flex;gap:10px;align-items:center;">'
        '<input type="color" name="brand_color" value="' + escape_html(bc) + '" style="width:48px;height:36px;border:none;background:none;cursor:pointer;border-radius:4px;"/>'
        '<span style="font-family:var(--mono);font-size:11px;color:var(--text3);">Primary brand color</span>'
        "</div></div>"
        '<div class="form-group">'
        '<label class="form-label">' + escape_html(_t(lang, "gen.brand_voice")) + "</label>"
        '<textarea class="form-textarea" name="brand_voice" style="min-height:60px;" placeholder="Describe your brand voice...">'
        + escape_html(bv) +
        "</textarea></div>"
        "</div>"

        '<div class="card mb-4">'
        '<div class="card-title">Advanced</div>'
        '<div class="form-group">'
        '<label class="form-label">Aspect Ratio (Video)</label>'
        '<select class="form-select" name="aspect_ratio">'
        '<option value="9:16" selected>9:16 - Vertical (Reels/TikTok)</option>'
        '<option value="1:1">1:1 - Square</option>'
        '<option value="16:9">16:9 - Landscape</option>'
        "</select></div>"
        '<div class="form-group">'
        '<label class="form-label">LLM API Key <span style="font-weight:400;color:var(--text3);">(optional)</span></label>'
        '<input class="form-input" type="password" name="llm_api_key" placeholder="Leave blank to use account key"/>'
        "</div>"
        '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;">'
        '<input type="checkbox" name="human_review" value="1" style="accent-color:var(--accent);width:15px;height:15px;"/>'
        + escape_html(_t(lang, "gen.human_review")) + " - pause before media generation"
        "</label>"
        "</div>"

        '<button class="btn btn-primary" style="width:100%;justify-content:center;font-size:15px;padding:14px;" type="submit" id="gen-btn">'
        + escape_html(_t(lang, "gen.submit")) +
        "</button>"
        "</div>"  # end right col

        "</div>"  # grid
        "</form>"
        "</div>"

        "<script>"
        "document.getElementById('gen-form').addEventListener('submit', function() {"
        "  var btn = document.getElementById('gen-btn');"
        "  btn.textContent = '" + escape_js(_t(lang, "gen.generating")) + "';"
        "  btn.disabled = true;"
        "});"
        "document.querySelectorAll('[name=content_type]').forEach(function(r) {"
        "  r.addEventListener('change', function() {"
        "    document.getElementById('lbl-static').style.borderColor = r.value === 'static' ? 'var(--accent)' : 'var(--border)';"
        "    document.getElementById('lbl-video').style.borderColor  = r.value === 'video'  ? 'var(--accent)' : 'var(--border)';"
        "  });"
        "});"
        "</script>"
    )
    return HTMLResponse(ui._page(content, user, _t(lang, "gen.title"), "generate", lang))


# ── Generate submit ────────────────────────────────────────────────────────────
@router.post("/generate")
async def generate_post(request: Request, background_tasks: BackgroundTasks,
                        topic: str = Form(""), content_type: str = Form("static"),
                        language: str = Form("English"), brand_color: str = Form("#4f8ef7"),
                        aspect_ratio: str = Form("9:16"), number_idea: int = Form(3),
                        human_review: str = Form(""), llm_api_key: str = Form(""),
                        brand_voice: str = Form(""), product_features: str = Form(""),
                        competitor_urls: str = Form("")):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    topic = topic.strip()
    if not topic:
        return RedirectResponse("/generate?msg=Topic+required", status_code=303)
    if not quota_ok_atomic(user):
        return RedirectResponse("/generate?msg=Quota+exceeded+-+upgrade+your+plan", status_code=303)

    form      = await request.form()
    platforms = list(form.getlist("platforms")) or ["Instagram"]
    settings  = get_user_settings(user["id"])
    brand     = get_default_brand(user["id"])
    bp        = get_brand_profile(user["id"])

    merged_bp = dict(bp)
    if brand:
        merged_bp.update(brand.get("profile", {}))
    if brand_voice.strip():
        merged_bp["brand_voice"] = brand_voice.strip()

    features  = [f.strip() for f in product_features.splitlines() if f.strip()]
    comp_urls = [u.strip() for u in competitor_urls.splitlines() if u.strip().startswith("http")]

    import os
    resolved_llm_key   = llm_api_key.strip() or settings.get("gemini_key", "") or os.getenv("GEMINI_API_KEY", "")
    resolved_img_key   = settings.get("gemini_key", "")  or os.getenv("GEMINI_API_KEY", "")
    resolved_video_key = settings.get("aiml_key", "")    or os.getenv("AIML_API_KEY", "")

    cfg = {
        "topic":            topic,
        "content_type":     content_type,
        "platforms":        platforms,
        "language":         language,
        "brand_color":      brand_color or "#4f8ef7",
        "aspect_ratio":     aspect_ratio,
        "number_idea":      max(1, min(int(number_idea), 10)),
        "niche":            detect_niche(topic),
        "human_review":     bool(human_review),
        "product_features": features,
        "competitor_urls":  comp_urls,
        "brand_profile":    merged_bp,
        "llm_provider":     settings.get("llm_provider", "google"),
        "llm_model":        settings.get("llm_model", "gemini-2.5-flash"),
        "image_model":      settings.get("image_model", "gemini-3.1-flash-image-preview"),
        "video_model":      settings.get("video_model", "google/veo-3.1-i2v"),
        "llm_api_key":      resolved_llm_key,
        "image_api_key":    resolved_img_key,
        "video_api_key":    resolved_video_key,
    }

    gid = create_generation(user["id"], topic, content_type, platforms, language, cfg)
    background_tasks.add_task(pipelines._run_pipeline, gid, user["id"], cfg)
    return RedirectResponse("/result/" + gid, status_code=303)


# ── Result page ────────────────────────────────────────────────────────────────
@router.get("/result/{gid}", response_class=HTMLResponse)
async def result_page(request: Request, gid: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    gen = get_generation(gid, user["id"])
    if not gen:
        return RedirectResponse("/history", status_code=303)

    lang, _ = _get_lang_and_settings(user)
    status  = gen["status"]

    # Still running
    if status in ("pending", "running", "generating_media"):
        spin_msgs = {
            "pending":          "Queued - starting pipeline...",
            "running":          "AI agents working - scraping trends, analyzing competitors...",
            "generating_media": "Generating media - creating visuals...",
        }
        spin_msg = spin_msgs.get(status, "Processing...")
        content = (
            '<div class="topbar"><div>'
            '<div class="topbar-title">Generating...</div>'
            '<div class="topbar-sub">' + escape_html(gen["topic"][:60]) + "</div>"
            "</div></div>"
            '<div class="content" style="display:flex;align-items:center;justify-content:center;min-height:60vh;">'
            '<div style="text-align:center;">'
            '<div class="spinner" style="width:48px;height:48px;border-width:3px;margin:0 auto 24px;"></div>'
            '<div style="font-size:15px;font-weight:600;margin-bottom:8px;">' + escape_html(spin_msg) + "</div>"
            '<div style="font-family:var(--mono);font-size:11px;color:var(--text3);">' + gid[:16] + "...</div>"
            '<div style="margin-top:24px;"><a class="btn btn-ghost btn-sm" href="/history">&larr; History</a></div>'
            "</div></div>"
            "<script>setTimeout(function(){location.replace(location.href);}, 3000);</script>"
        )
        return HTMLResponse(ui._page(content, user, "Generating...", "generate", lang))

    # Failed
    if status == "failed":
        err = escape_html((gen.get("error") or "Unknown error")[:300])
        content = (
            '<div class="topbar"><div><div class="topbar-title">Generation Failed</div></div>'
            '<a class="btn btn-ghost" href="/generate">&larr; Try again</a></div>'
            '<div class="content">'
            '<div class="alert alert-danger">Failed: ' + err + "</div>"
            '<div style="text-align:center;margin-top:40px;">'
            '<a class="btn btn-primary" href="/generate">New Generation</a>'
            "</div></div>"
        )
        return HTMLResponse(ui._page(content, user, "Failed", "generate", lang))

    # Awaiting human approval
    if status == "awaiting_approval":
        result     = gen.get("result") or {}
        ideas      = result.get("ideas", [])
        ideas_html = ui._build_ideas_html(gen)
        n          = len(ideas)
        gid_js     = escape_js(gid)
        content = (
            "<div class=\"topbar\">"
            "<div><div class=\"topbar-title\">Review Ideas</div>"
            "<div class=\"topbar-sub\">" + escape_html(gen["topic"][:60]) + "</div></div>"
            "<div class=\"flex gap-2\">"
            "<a class=\"btn btn-ghost\" href=\"/generate\">&larr; New</a>"
            "<button class=\"btn btn-primary\" onclick=\"approveAllIndividual('" + gid_js + "'," + str(n) + ")\">"
            "Approve All (" + str(n) + ")"
            "</button>"
            "</div></div>"
            "<div class=\"content\">" + ideas_html + "</div>"
        )
        return HTMLResponse(ui._page(content, user, "Review Ideas", "generate", lang))

    # Completed / partial
    result     = gen.get("result") or {}
    ideas_html = ui._build_ideas_html(gen)
    comp_html  = ui._build_competitor_report_html(result, gid)

    warnings = ""
    if result.get("warning"):
        warnings = (
            '<div class="alert alert-warn mb-3" style="font-size:12px;">'
            + escape_html(result["warning"]) + "</div>"
        )
    if gen.get("fallback_used"):
        fallback_msg = _t(lang, "gen.fallback_warn")
        warnings = (
            '<div class="alert alert-warn mb-3" style="font-size:12px;">'
            + escape_html(fallback_msg) + "</div>"
            + warnings
        )

    plats = ", ".join(gen.get("platforms") or [])
    content = (
        "<div class=\"topbar\">"
        "<div><div class=\"topbar-title\">" + escape_html(gen["topic"][:50]) + "</div>"
        "<div class=\"topbar-sub\">" + escape_html(plats[:60]) + " - " + escape_html(gen["content_type"]) + " - " + escape_html(gen["language"]) + "</div></div>"
        "<div class=\"flex gap-2\">"
        "<a class=\"btn btn-ghost\" href=\"/generate\">&larr; New</a>"
        "<a class=\"btn btn-ghost btn-sm\" href=\"/history\">History</a>"
        "</div></div>"
        "<div class=\"content\">"
        + warnings + comp_html + ideas_html +
        "</div>"
    )
    return HTMLResponse(ui._page(content, user, gen["topic"][:40], "generate", lang))


# ── History ────────────────────────────────────────────────────────────────────
@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    lang, _ = _get_lang_and_settings(user)
    gens    = get_user_generations(user["id"], limit=200)

    rows = ""
    for g in gens:
        badge      = STATUS_BADGE.get(g["status"], "badge-gray")
        status_lbl = g["status"].replace("_", " ")
        ct_icon    = "Video" if g["content_type"] == "video" else "Static"
        plats      = ", ".join(g.get("platforms") or [])[:30]

        fallback_span = ""
        if g.get("fallback_used"):
            fallback_span = ' <span class="badge badge-amber" style="font-size:9px;">fallback</span>'

        rows += (
            "<tr>"
            '<td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
            + escape_html(g["topic"]) + "</td>"
            "<td>" + escape_html(ct_icon) + "</td>"
            "<td>" + escape_html(plats) + "</td>"
            '<td><span class="badge ' + badge + '">' + escape_html(status_lbl) + "</span>"
            + fallback_span + "</td>"
            '<td style="font-family:var(--mono);font-size:10px;color:var(--text3);">'
            + g["created_at"][:16] + "</td>"
            '<td><a class="btn btn-ghost btn-sm" href="/result/' + g["id"] + '">View</a></td>'
            "</tr>"
        )

    if not rows:
        rows = (
            '<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:32px;">'
            + escape_html(_t(lang, "hist.no_gens")) + "</td></tr>"
        )

    content = (
        "<div class=\"topbar\">"
        "<div><div class=\"topbar-title\">" + escape_html(_t(lang, "hist.title")) +
        " <span style=\"font-family:var(--mono);font-size:13px;color:var(--text3);\">(" + str(len(gens)) + ")</span></div></div>"
        "<a class=\"btn btn-primary\" href=\"/generate\">" + escape_html(_t(lang, "action.generate")) + "</a>"
        "</div>"
        "<div class=\"content\">"
        "<div class=\"table-wrap\">"
        "<table class=\"hist-table\"><thead><tr>"
        "<th>" + escape_html(_t(lang, "hist.topic")) + "</th>"
        "<th>" + escape_html(_t(lang, "hist.type")) + "</th>"
        "<th>" + escape_html(_t(lang, "gen.platforms")) + "</th>"
        "<th>" + escape_html(_t(lang, "hist.status")) + "</th>"
        "<th>" + escape_html(_t(lang, "hist.date")) + "</th>"
        "<th></th>"
        "</tr></thead><tbody>" + rows + "</tbody></table>"
        "</div></div>"
    )
    return HTMLResponse(ui._page(content, user, _t(lang, "hist.title"), "history", lang))
