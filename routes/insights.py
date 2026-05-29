"""routes/insights.py — Trend and competitor intelligence panel."""
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import get_current_user, escape_html
from db import get_user_settings
from core.i18n import normalize_lang, t as _t
import ui

router = APIRouter()


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(request: Request, tab: str = "trend", gen_id: str = ""):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    s    = get_user_settings(user["id"])
    lang = normalize_lang(s.get("ui_language","en"))

    # Load latest insights from generations
    all_insights = ui._get_latest_insights(user["id"], limit=20)

    has_comp  = any(ins.get("has_comp")  for ins in all_insights)
    has_trend = any(ins.get("has_trend") for ins in all_insights)

    # Pick the data to show
    comp_data  = None
    trend_data = None

    if gen_id:
        selected = next((ins for ins in all_insights if ins["id"] == gen_id), None)
        if selected:
            comp_data  = selected.get("competitor")
            trend_data = selected.get("trend")
    else:
        for ins in all_insights:
            if ins.get("has_comp") and not comp_data:
                comp_data = ins["competitor"]
            if ins.get("has_trend") and not trend_data:
                trend_data = ins["trend"]

    # Tab selector
    tabs = [
        ("trend",      "📈", _t(lang,"insights.trend")),
        ("competitor", "🔍", _t(lang,"insights.competitor")),
    ]
    tab_html = "".join(
        f'<a class="tab-pill {"active" if tab==k else ""}" href="/insights?tab={k}">{icon} {label}</a>'
        for k, icon, label in tabs
    )

    # Source selector (recent generations with insights)
    sources = [ins for ins in all_insights if (ins.get("has_comp") or ins.get("has_trend"))]
    src_opts = "".join(
        f'<option value="{ins["id"]}" {"selected" if ins["id"]==gen_id else ""}>'
        f'{ins["topic"][:50]} ({ins["created_at"][:10]})</option>'
        for ins in sources[:20]
    )
    src_select = (
        f'<select class="form-select" style="width:320px;font-size:12px;" '
        f'onchange="window.location=\'/insights?tab={tab}&gen_id=\'+this.value">'
        f'<option value="">Latest insights</option>{src_opts}</select>'
    ) if sources else ""

    if tab == "competitor":
        panel = ui._render_competitor_panel(comp_data)
    else:
        panel = ui._render_trend_panel(trend_data)

    if not has_comp and not has_trend:
        panel = f'''<div class="card">
          <div class="empty-state" style="padding:60px 20px;">
            <div class="empty-icon">◎</div>
            <div class="empty-text">{_t(lang,"insights.title")} — No data yet</div>
            <div class="empty-sub">Generate content with competitor URLs or trends to populate this panel.</div>
            <div style="margin-top:20px;"><a class="btn btn-primary" href="/generate">✦ Generate Content</a></div>
          </div>
        </div>'''

    content = f"""
    <div class="topbar">
      <div><div class="topbar-title">{_t(lang,"insights.title")}</div></div>
      {src_select}
    </div>
    <div class="content">
      <div class="tab-pills">{tab_html}</div>
      {panel}
    </div>"""
    return HTMLResponse(ui._page(content, user, _t(lang,"insights.title"), "insights", lang))
