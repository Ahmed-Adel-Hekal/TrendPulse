"""routes/account.py — Account settings, API keys, plan display."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from urllib.parse import quote_plus

from auth import get_current_user, escape_html, hash_password, verify_password, password_validation_error
from db import (get_user_settings, save_user_settings, get_conn, quota_status,
                PLAN_QUOTAS, PLAN_PRICES, get_usage_this_month)
from core.i18n import normalize_lang, t as _t, SUPPORTED_LANGUAGES
import ui

router = APIRouter()


def _get_lang(user):
    s = get_user_settings(user["id"])
    return normalize_lang(s.get("ui_language","en"))


# ── Account page ───────────────────────────────────────────────────────────────
@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, msg: str = "", error: str = ""):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    lang     = _get_lang(user)
    settings = get_user_settings(user["id"])
    q        = quota_status(user)
    pct      = round(q["used"] / max(q["limit"],1) * 100)

    msg_html = f'<div class="alert alert-success mb-3">✓ {escape_html(msg)}</div>' if msg else ""
    err_html = f'<div class="alert alert-danger mb-3">✕ {escape_html(error)}</div>' if error else ""

    # Language selector
    lang_opts = "".join(
        f'<option value="{code}" {"selected" if code==settings.get("ui_language","en") else ""}>'
        f'{info["flag"]} {info["label"]}</option>'
        for code, info in SUPPORTED_LANGUAGES.items()
    )

    provider_opts = "".join(
        f'<option value="{v}" {"selected" if v==settings.get("llm_provider","google") else ""}>{l}</option>'
        for v,l in [("google","Google Gemini"),("openrouter","OpenRouter")]
    )

    content = f"""
    <div class="topbar">
      <div><div class="topbar-title">{_t(lang,"acct.title")}</div></div>
    </div>
    <div class="content">
      {msg_html}{err_html}
      <div class="grid-2" style="gap:20px;align-items:start;">
        <div>
          <!-- Profile -->
          <div class="card mb-4">
            <div class="card-title">👤 {_t(lang,"acct.profile")}</div>
            <form method="post" action="/account/profile">
              <div class="form-group">
                <label class="form-label">{_t(lang,"acct.full_name")}</label>
                <input class="form-input" name="name" value="{escape_html(user['name'])}"/>
              </div>
              <div class="form-group">
                <label class="form-label">{_t(lang,"acct.email")}</label>
                <input class="form-input" type="email" name="email" value="{escape_html(user['email'])}"/>
              </div>
              <button class="btn btn-primary btn-sm" type="submit">{_t(lang,"acct.save_changes")}</button>
            </form>
          </div>
          <!-- Password -->
          <div class="card mb-4">
            <div class="card-title">🔑 {_t(lang,"acct.password")}</div>
            <form method="post" action="/account/password">
              <div class="form-group">
                <label class="form-label">Current Password</label>
                <input class="form-input" type="password" name="current_password" required/>
              </div>
              <div class="form-group">
                <label class="form-label">New Password</label>
                <input class="form-input" type="password" name="new_password" required minlength="8"/>
              </div>
              <button class="btn btn-ghost btn-sm" type="submit">Update Password</button>
            </form>
          </div>
          <!-- Language -->
          <div class="card">
            <div class="card-title">🌐 {_t(lang,"acct.ui_language")}</div>
            <form method="post" action="/account/settings">
              <div class="form-group">
                <label class="form-label">{_t(lang,"lang.label")}</label>
                <select class="form-select" name="ui_language">{lang_opts}</select>
                <div class="form-hint">Changes the interface language globally</div>
              </div>
              <input type="hidden" name="_lang_only" value="1"/>
              <button class="btn btn-primary btn-sm" type="submit">{_t(lang,"action.save")}</button>
            </form>
          </div>
        </div>
        <div>
          <!-- Usage -->
          <div class="card mb-4">
            <div class="card-title">📊 {_t(lang,"acct.usage")}</div>
            <div style="margin-bottom:12px;">
              <div style="display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px;margin-bottom:6px;">
                <span>{q["used"]} {_t(lang,"quota.used")}</span>
                <span>{q["limit"]} limit · {q["plan"].upper()}</span>
              </div>
              <div class="progress"><div class="progress-bar" style="width:{pct}%;{"background:var(--red)" if pct>=90 else ""}"></div></div>
            </div>
            <a class="btn btn-ghost btn-sm" href="/pricing">{_t(lang,"alert.upgrade")}</a>
          </div>
          <!-- API Keys -->
          <div class="card mb-4">
            <div class="card-title">🔑 {_t(lang,"acct.api_keys")}</div>
            <form method="post" action="/account/settings">
              <div class="form-group">
                <label class="form-label">LLM Provider</label>
                <select class="form-select" name="llm_provider">{provider_opts}</select>
              </div>
              <div class="form-group">
                <label class="form-label">Gemini API Key</label>
                <input class="form-input" type="password" name="gemini_key"
                  value="{escape_html(settings.get('gemini_key',''))}"
                  placeholder="AIza…"/>
              </div>
              <div class="form-group">
                <label class="form-label">OpenRouter API Key</label>
                <input class="form-input" type="password" name="openrouter_key"
                  value="{escape_html(settings.get('openrouter_key',''))}"
                  placeholder="sk-or-…"/>
              </div>
              <div class="form-group">
                <label class="form-label">AIML API Key (Video)</label>
                <input class="form-input" type="password" name="aiml_key"
                  value="{escape_html(settings.get('aiml_key',''))}"
                  placeholder="AIML key for Veo 3.1"/>
              </div>
              <div class="form-group">
                <label class="form-label">LLM Model</label>
                <input class="form-input" name="llm_model" value="{escape_html(settings.get('llm_model','gemini-2.5-flash'))}"/>
              </div>
              <button class="btn btn-primary btn-sm" type="submit">{_t(lang,"acct.save_changes")}</button>
            </form>
          </div>
        </div>
      </div>
    </div>"""
    return HTMLResponse(ui._page(content, user, _t(lang,"acct.title"), "account", lang))


@router.post("/account/profile")
async def account_profile_save(request: Request,
                                name: str = Form(""), email: str = Form("")):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    name  = name.strip()
    email = email.strip().lower()
    if name and email:
        with get_conn() as conn:
            conn.execute("UPDATE users SET name=?, email=? WHERE id=?",
                         (name, email, user["id"]))
    return RedirectResponse("/account?msg=Profile+updated", status_code=303)


@router.post("/account/password")
async def account_password_save(request: Request,
                                 current_password: str = Form(""),
                                 new_password: str = Form("")):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    if not verify_password(current_password, user["password_hash"]):
        return RedirectResponse("/account?error=Current+password+incorrect", status_code=303)
    password_error = password_validation_error(new_password)
    if password_error:
        return RedirectResponse("/account?error=" + quote_plus(password_error), status_code=303)

    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                     (hash_password(new_password), user["id"]))
    return RedirectResponse("/account?msg=Password+updated", status_code=303)


@router.post("/account/settings")
async def account_settings_save(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    form     = await request.form()
    settings = get_user_settings(user["id"])

    # If this is language-only save, just update that field
    if form.get("_lang_only"):
        ui_lang = normalize_lang(str(form.get("ui_language","en")))
        settings["ui_language"] = ui_lang
        save_user_settings(user["id"], settings)
        return RedirectResponse("/account?msg=Language+updated", status_code=303)

    settings.update({
        "gemini_key":     str(form.get("gemini_key","")).strip(),
        "openrouter_key": str(form.get("openrouter_key","")).strip(),
        "aiml_key":       str(form.get("aiml_key","")).strip(),
        "llm_provider":   str(form.get("llm_provider","google")),
        "llm_model":      str(form.get("llm_model","gemini-2.5-flash")).strip(),
        "ui_language":    normalize_lang(str(form.get("ui_language", settings.get("ui_language","en")))),
    })
    save_user_settings(user["id"], settings)
    return RedirectResponse("/account?msg=Settings+saved", status_code=303)


# ── Pricing page ───────────────────────────────────────────────────────────────
@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)

    lang = _get_lang(user)

    plans = [
        ("free",    "$0",   "10",    ["10 generations/month","Static posts only","1 platform"]),
        ("starter", "$19",  "50",    ["50 generations/month","Static + video","3 platforms","Competitor analysis"]),
        ("pro",     "$49",  "200",   ["200 generations/month","All content types","All platforms","Trend intelligence","Strategy calendar","Priority support"]),
        ("agency",  "$149", "1,000", ["1,000 generations/month","Everything in Pro","White-label reports","API access","Dedicated support"]),
    ]

    cards = ""
    for plan, price, quota, features in plans:
        is_current = user.get("plan") == plan
        feature_list = "".join(
            f'<li style="padding:4px 0;font-size:13px;color:var(--text2);">✓ {f}</li>'
            for f in features
        )
        cards += f"""
        <div class="card" style="{"border-color:var(--accent);" if is_current else ""}text-align:center;">
          <div style="font-weight:800;font-size:16px;text-transform:capitalize;margin-bottom:4px;">{plan.title()}</div>
          <div style="font-size:32px;font-weight:900;color:var(--accent);margin-bottom:2px;">{price}<span style="font-size:13px;color:var(--text3);">/mo</span></div>
          <div style="font-family:var(--mono);font-size:11px;color:var(--text3);margin-bottom:16px;">{quota} generations</div>
          <ul style="list-style:none;text-align:left;margin-bottom:20px;">{feature_list}</ul>
          {"<span class='badge badge-green' style='font-size:11px;'>Current plan</span>" if is_current else
           f"<button class='btn btn-primary' style='width:100%;justify-content:center;' onclick='selectPlan(\"{plan}\")'>{_t(lang,'alert.upgrade')}</button>"}
        </div>"""

    content = f"""
    <div class="topbar">
      <div><div class="topbar-title">{_t(lang,"pricing.title")}</div>
        <div class="topbar-sub">{_t(lang,"pricing.current")}: {user.get("plan","free").title()}</div></div>
    </div>
    <div class="content">
      <div class="grid-4" style="gap:16px;">{cards}</div>
    </div>
    <script>
    function selectPlan(plan){{
      toast('Stripe billing coming soon — contact us at support@signalmind.ai','info');
    }}
    </script>"""
    return HTMLResponse(ui._page(content, user, _t(lang,"pricing.title"), "pricing", lang))
