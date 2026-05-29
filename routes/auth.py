"""routes/auth.py — Login, register, logout, dashboard."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from urllib.parse import quote_plus

from auth import (verify_password, create_token, escape_html,
                  update_last_login, TOKEN_EXPIRE, password_validation_error)
from db import get_user_by_email, create_user, quota_status, get_user_settings, get_user_generations, get_calendar_items
from core.i18n import normalize_lang, t as _t
import ui

router = APIRouter()


# ── Login ──────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "", next: str = ""):
    err_html = ""
    if error:
        err_html = '<div class="alert alert-danger" style="margin-bottom:20px;">' + escape_html(error) + "</div>"

    content = (
        '<div class="auth-center">'
        '<div class="auth-card">'
        '<div class="auth-logo">'
        '<div class="auth-logo-icon">⚡</div>'
        '<div class="auth-title">Welcome back</div>'
        '<div class="auth-sub">Sign in to your TrendPulse workspace</div>'
        "</div>"
        + err_html +
        '<form method="post" action="/login">'
        '<input type="hidden" name="next" value="' + escape_html(next) + '"/>'
        '<div class="form-group">'
        '<label class="form-label">Email</label>'
        '<input class="form-input" type="email" name="email" placeholder="you@example.com" required autofocus/>'
        "</div>"
        '<div class="form-group">'
        '<label class="form-label">Password</label>'
        '<input class="form-input" type="password" name="password" placeholder="••••••••" required/>'
        "</div>"
        '<button class="btn btn-primary" style="width:100%;justify-content:center;padding:12px;font-size:14px;" type="submit">'
        "Sign in &rarr;"
        "</button>"
        "</form>"
        '<div style="text-align:center;margin-top:24px;font-size:13px;color:var(--text3);">'
        'No account? <a href="/register" style="color:var(--accent);text-decoration:none;font-weight:500;">Create one</a>'
        "</div>"
        "</div></div>"
    )
    return HTMLResponse(ui._auth_page(content, "Sign in"))


@router.post("/login")
async def login_post(request: Request,
                     email: str = Form(""), password: str = Form(""),
                     next: str = Form("/dashboard")):
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return RedirectResponse("/login?error=Invalid+email+or+password", status_code=303)
    if user.get("is_banned"):
        reason = user.get("ban_reason", "")
        msg = "Account suspended" + (": " + reason if reason else "")
        return RedirectResponse("/login?error=" + escape_html(msg), status_code=303)

    update_last_login(user["id"])
    token    = create_token(user["id"])
    redirect = next if next.startswith("/") else "/dashboard"
    response = RedirectResponse(redirect, status_code=303)
    response.set_cookie("sm_token", token, httponly=True, samesite="lax",
                        max_age=TOKEN_EXPIRE * 60)
    return response


# ── Register ───────────────────────────────────────────────────────
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = ""):
    err_html = ""
    if error:
        err_html = '<div class="alert alert-danger" style="margin-bottom:20px;">' + escape_html(error) + "</div>"

    content = (
        '<div class="auth-center">'
        '<div class="auth-card">'
        '<div class="auth-logo">'
        '<div class="auth-logo-icon">⚡</div>'
        '<div class="auth-title">Create account</div>'
        '<div class="auth-sub">Start generating AI content today</div>'
        "</div>"
        + err_html +
        '<form method="post" action="/register">'
        '<div class="form-group">'
        '<label class="form-label">Full Name</label>'
        '<input class="form-input" type="text" name="name" placeholder="Your name" required autofocus/>'
        "</div>"
        '<div class="form-group">'
        '<label class="form-label">Email</label>'
        '<input class="form-input" type="email" name="email" placeholder="you@example.com" required/>'
        "</div>"
        '<div class="form-group">'
        '<label class="form-label">Password</label>'
        '<input class="form-input" type="password" name="password" placeholder="Min 8 characters" required minlength="8"/>'
        "</div>"
        '<button class="btn btn-primary" style="width:100%;justify-content:center;padding:12px;font-size:14px;" type="submit">'
        "Create account &rarr;"
        "</button>"
        "</form>"
        '<div style="text-align:center;margin-top:24px;font-size:13px;color:var(--text3);">'
        'Already have an account? <a href="/login" style="color:var(--accent);text-decoration:none;font-weight:500;">Sign in</a>'
        "</div>"
        "</div></div>"
    )
    return HTMLResponse(ui._auth_page(content, "Register"))


@router.post("/register")
async def register_post(request: Request,
                        name: str = Form(""), email: str = Form(""),
                        password: str = Form("")):
    name  = name.strip()
    email = email.strip().lower()
    if not name or not email:
        return RedirectResponse("/register?error=All+fields+required", status_code=303)
    password_error = password_validation_error(password)
    if password_error:
        return RedirectResponse("/register?error=" + quote_plus(password_error), status_code=303)
    if get_user_by_email(email):
        return RedirectResponse("/register?error=Email+already+registered", status_code=303)
    try:
        user  = create_user(email, name, password)
        token = create_token(user["id"])
        resp  = RedirectResponse("/generate", status_code=303)
        resp.set_cookie("sm_token", token, httponly=True, samesite="lax",
                        max_age=TOKEN_EXPIRE * 60)
        return resp
    except Exception as e:
        return RedirectResponse("/register?error=" + quote_plus(str(e)[:120]), status_code=303)


# ── Logout ─────────────────────────────────────────────────────────
@router.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("sm_token")
    return resp


# ── Root ───────────────────────────────────────────────────────────
@router.get("/")
async def root(request: Request):
    from auth import get_current_user
    user = get_current_user(request)
    return RedirectResponse("/dashboard" if user else "/login", status_code=303)


# ── Dashboard ──────────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    from auth import get_current_user
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    settings = get_user_settings(user["id"])
    lang     = normalize_lang(settings.get("ui_language", "en"))
    gens     = get_user_generations(user["id"], limit=6)
    q        = quota_status(user)
    pct      = round(q["used"] / max(q["limit"], 1) * 100)

    import datetime as _dt
    now = _dt.datetime.utcnow()
    cal = get_calendar_items(user["id"], now.year, now.month)

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

    gen_rows = ""
    for g in gens:
        badge  = STATUS_BADGE.get(g["status"], "badge-gray")
        slabel = g["status"].replace("_", " ")
        ct_lbl = "Video" if g["content_type"] == "video" else "Static"
        gen_rows += (
            "<tr>"
            '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;">'
            + escape_html(g["topic"]) + "</td>"
            "<td>" + escape_html(ct_lbl) + "</td>"
            '<td><span class="badge ' + badge + '">' + escape_html(slabel) + "</span></td>"
            '<td style="font-family:var(--mono);font-size:10px;color:var(--text3);">' + g["created_at"][:10] + "</td>"
            '<td><a class="btn btn-ghost btn-sm" href="/result/' + g["id"] + '">View</a></td>'
            "</tr>"
        )
    if not gen_rows:
        gen_rows = (
            '<tr><td colspan="5" style="text-align:center;color:var(--text3);padding:28px;">'
            + escape_html(_t(lang, "hist.no_gens")) + "</td></tr>"
        )

    upcoming = [c for c in cal if c["status"] == "scheduled"][:5]
    PLAT_ICONS = {"Instagram":"📸","TikTok":"🎬","LinkedIn":"💼","Twitter/X":"🐦","Facebook":"👥"}
    cal_rows = ""
    for c in upcoming:
        icon = PLAT_ICONS.get(c["platform"], "📱")
        cal_rows += (
            "<tr>"
            "<td>" + icon + " " + escape_html(c["platform"]) + "</td>"
            '<td style="font-weight:500;">' + escape_html(c["title"][:45]) + "</td>"
            '<td style="font-family:var(--mono);font-size:10px;color:var(--text3);">' + c["publish_date"] + "</td>"
            "</tr>"
        )
    if not cal_rows:
        cal_rows = '<tr><td colspan="3" style="text-align:center;color:var(--text3);padding:24px;">No scheduled posts</td></tr>'

    all_gens   = get_user_generations(user["id"], limit=500)
    total      = len(all_gens)
    completed  = len([g for g in all_gens if g["status"] == "completed"])
    first_name = escape_html(user["name"].split()[0])

    content = (
        '<div class="topbar">'
        "<div>"
        '<div class="topbar-title">' + escape_html(_t(lang, "dash.welcome")) + ", " + first_name + " 👋</div>"
        '<div class="topbar-sub">' + escape_html(_t(lang, "quota.label")) + ": " + str(q["used"]) + "/" + str(q["limit"]) + " · " + str(pct) + "% used</div>"
        "</div>"
        '<a class="btn btn-primary" href="/generate">✦ ' + escape_html(_t(lang, "action.generate")) + "</a>"
        "</div>"

        "<div class=\"content\">"

        # Stat row
        '<div class="grid-4 mb-4">'
        '<div class="stat-card">'
        '<div class="stat-label">' + escape_html(_t(lang, "dash.total_gens")) + "</div>"
        '<div class="stat-value">' + str(total) + "</div>"
        "</div>"
        '<div class="stat-card">'
        '<div class="stat-label">' + escape_html(_t(lang, "dash.completed")) + "</div>"
        '<div class="stat-value" style="color:var(--green);">' + str(completed) + "</div>"
        "</div>"
        '<div class="stat-card">'
        '<div class="stat-label">Quota Left</div>'
        '<div class="stat-value" style="color:var(--accent);">' + str(q["remaining"]) + "</div>"
        '<div class="stat-sub">' + escape_html(q["plan"]) + " plan</div>"
        "</div>"
        '<div class="stat-card">'
        '<div class="stat-label">' + escape_html(_t(lang, "dash.scheduled")) + "</div>"
        '<div class="stat-value" style="color:var(--blue);">' + str(len(upcoming)) + "</div>"
        "</div>"
        "</div>"

        # Quota progress
        '<div class="card mb-4" style="padding:16px 22px;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
        '<span style="font-size:12px;font-weight:600;color:var(--text2);">Monthly Quota</span>'
        '<span style="font-family:var(--mono);font-size:11px;color:var(--text3);">' + str(q["used"]) + " / " + str(q["limit"]) + "</span>"
        "</div>"
        '<div class="progress"><div class="progress-bar" style="width:' + str(pct) + '%;'
        + ("background:var(--red);" if pct >= 90 else "") + '"></div></div>'
        + ('<div style="margin-top:10px;"><a class="btn btn-ghost btn-sm" href="/pricing">↑ Upgrade plan</a></div>' if pct >= 80 else "")
        + "</div>"

        # Two columns
        '<div class="grid-2" style="gap:20px;">'

        # Recent gens
        '<div class="card" style="padding:0;overflow:hidden;">'
        '<div style="padding:14px 20px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">'
        '<span style="font-size:12px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px;">' + escape_html(_t(lang, "dash.recent")) + "</span>"
        '<a class="btn btn-ghost btn-sm" href="/history">All &rarr;</a>'
        "</div>"
        '<table><tbody>' + gen_rows + "</tbody></table>"
        "</div>"

        # Upcoming cal
        '<div class="card" style="padding:0;overflow:hidden;">'
        '<div style="padding:14px 20px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">'
        '<span style="font-size:12px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px;">' + escape_html(_t(lang, "dash.upcoming")) + "</span>"
        '<a class="btn btn-ghost btn-sm" href="/calendar">Calendar &rarr;</a>'
        "</div>"
        '<table><tbody>' + cal_rows + "</tbody></table>"
        "</div>"

        "</div></div>"
    )
    return HTMLResponse(ui._page(content, user, _t(lang, "dash.welcome"), "dashboard", lang))
