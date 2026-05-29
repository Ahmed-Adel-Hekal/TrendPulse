"""routes/admin.py — Full admin panel with all privileges."""
from __future__ import annotations
import json
import os
import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import get_current_user, escape_html, escape_js
from db import (
    get_conn, get_all_users, get_all_generations_admin,
    update_user_plan, set_user_admin, ban_user, unban_user, delete_user_admin,
    get_generation_admin, update_generation, get_system_stats,
    get_admin_logs, log_admin_action, get_all_system_settings,
    set_system_setting, cancel_scheduled_generation, quota_status,
    PLAN_QUOTAS, OUTPUT_ROOT, now_iso, safe_json_loads,
)
from core.i18n import t as _t, is_rtl, get_dir, get_font, get_language_info, SUPPORTED_LANGUAGES

router = APIRouter(prefix="/admin")

# ── Auth guard ─────────────────────────────────────────────────────────────────
def _require_admin(request: Request):
    user = get_current_user(request)
    if not user:
        return None, RedirectResponse("/login", status_code=303)
    if not user.get("is_admin"):
        return None, RedirectResponse("/dashboard", status_code=303)
    return user, None


def _get_lang(user):
    from db import get_user_settings
    s = get_user_settings(user["id"])
    return s.get("ui_language", "en")


# ── CSS + HTML helpers ─────────────────────────────────────────────────────────
ADMIN_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');
:root{
  --bg:#05080f;--bg2:#090d18;--surface:#0e1526;--surface2:#131c30;
  --border:rgba(99,179,237,0.10);--border2:rgba(99,179,237,0.22);
  --accent:#4f8ef7;--accent2:#7c5af0;--green:#22c55e;--amber:#f59e0b;
  --red:#ef4444;--pink:#ec4899;--orange:#f97316;
  --text:#e8edf5;--text2:#8fa3c0;--text3:#4a5e78;
  --mono:'JetBrains Mono',monospace;--sans:'Outfit',sans-serif;
  --r:14px;--r2:8px;--shadow:0 4px 24px rgba(0,0,0,0.5);
  --admin-accent:#f97316;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
html{scroll-behavior:smooth;}
body{font-family:var(--sans);background:var(--bg);color:var(--text);min-height:100vh;}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(249,115,22,0.015) 1px,transparent 1px),linear-gradient(90deg,rgba(249,115,22,0.015) 1px,transparent 1px);background-size:48px 48px;pointer-events:none;z-index:0;}
::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:transparent;}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px;}
.layout{display:flex;min-height:100vh;position:relative;z-index:1;}
.sidebar{width:240px;flex-shrink:0;background:var(--bg2);border-right:1px solid rgba(249,115,22,0.15);display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:50;}
.sidebar-logo{padding:20px 16px;border-bottom:1px solid rgba(249,115,22,0.15);display:flex;align-items:center;gap:10px;}
.logo-icon{width:36px;height:36px;background:linear-gradient(135deg,var(--orange),var(--red));border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;}
.logo-text{font-size:16px;font-weight:800;letter-spacing:-0.5px;}
.logo-badge{font-family:var(--mono);font-size:9px;background:rgba(249,115,22,0.15);color:var(--orange);border:1px solid rgba(249,115,22,0.3);padding:2px 7px;border-radius:20px;margin-left:auto;}
.sidebar-nav{flex:1;padding:8px;overflow-y:auto;}
.nav-section{font-family:var(--mono);font-size:9px;color:var(--text3);letter-spacing:1.5px;text-transform:uppercase;padding:10px 10px 4px;}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:var(--r2);color:var(--text2);font-size:13px;font-weight:500;text-decoration:none;transition:all 0.15s;cursor:pointer;border:none;background:none;width:100%;}
.nav-item:hover{background:rgba(249,115,22,0.06);color:var(--text);}
.nav-item.active{background:rgba(249,115,22,0.12);color:var(--orange);}
.nav-item.active::before{content:'';position:absolute;left:0;top:20%;bottom:20%;width:2px;background:var(--orange);border-radius:2px;}
.nav-item{position:relative;}
.nav-icon{font-size:14px;width:18px;text-align:center;}
.sidebar-footer{padding:12px;border-top:1px solid rgba(249,115,22,0.15);}
.user-row{display:flex;align-items:center;gap:10px;padding:8px;border-radius:var(--r2);background:var(--surface);border:1px solid var(--border);}
.user-avatar{width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,var(--orange),var(--red));display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0;}
.user-info{flex:1;min-width:0;}
.user-name{font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.user-plan{font-family:var(--mono);font-size:10px;color:var(--orange);text-transform:uppercase;}
.main{margin-left:240px;flex:1;min-height:100vh;}
.topbar{position:sticky;top:0;background:rgba(5,8,15,0.9);backdrop-filter:blur(20px);border-bottom:1px solid rgba(249,115,22,0.1);padding:14px 28px;display:flex;align-items:center;justify-content:space-between;z-index:40;}
.topbar-title{font-size:16px;font-weight:700;}
.topbar-sub{font-family:var(--mono);font-size:10px;color:var(--text3);}
.content{padding:24px 28px;max-width:1400px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:20px;}
.card-title{font-size:14px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px;}
.stats-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:24px;}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:16px;transition:border-color 0.2s;}
.stat-card:hover{border-color:var(--border2);}
.stat-label{font-family:var(--mono);font-size:9px;color:var(--text3);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;}
.stat-value{font-size:26px;font-weight:800;line-height:1;}
.stat-sub{font-size:11px;color:var(--text3);margin-top:4px;font-family:var(--mono);}
.table-wrap{overflow:hidden;border-radius:var(--r);border:1px solid var(--border);}
table{width:100%;border-collapse:collapse;}
th{padding:9px 14px;text-align:left;font-family:var(--mono);font-size:10px;color:var(--text3);letter-spacing:1px;text-transform:uppercase;border-bottom:1px solid var(--border);background:var(--bg2);}
td{padding:11px 14px;border-bottom:1px solid var(--border);font-size:13px;}
tr:hover td{background:rgba(249,115,22,0.02);}
tr:last-child td{border-bottom:none;}
.badge{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:20px;font-family:var(--mono);font-size:10px;font-weight:500;}
.badge-blue{background:rgba(79,142,247,0.12);color:var(--accent);}
.badge-green{background:rgba(34,197,94,0.12);color:var(--green);}
.badge-amber{background:rgba(245,158,11,0.12);color:var(--amber);}
.badge-red{background:rgba(239,68,68,0.12);color:var(--red);}
.badge-gray{background:rgba(148,163,184,0.08);color:var(--text3);}
.badge-orange{background:rgba(249,115,22,0.15);color:var(--orange);}
.badge-purple{background:rgba(124,90,240,0.12);color:var(--accent2);}
.btn{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:var(--r2);font-family:var(--sans);font-size:12px;font-weight:600;border:none;cursor:pointer;transition:all 0.18s;text-decoration:none;white-space:nowrap;}
.btn-primary{background:linear-gradient(135deg,var(--orange),var(--red));color:#fff;}
.btn-primary:hover{opacity:0.88;transform:translateY(-1px);}
.btn-ghost{background:rgba(249,115,22,0.06);color:var(--orange);border:1px solid rgba(249,115,22,0.2);}
.btn-ghost:hover{background:rgba(249,115,22,0.12);}
.btn-danger{background:rgba(239,68,68,0.1);color:var(--red);border:1px solid rgba(239,68,68,0.2);}
.btn-danger:hover{background:rgba(239,68,68,0.2);}
.btn-green{background:rgba(34,197,94,0.1);color:var(--green);border:1px solid rgba(34,197,94,0.2);}
.btn-green:hover{background:rgba(34,197,94,0.2);}
.btn-sm{padding:4px 10px;font-size:11px;}
.flex{display:flex;}.items-center{align-items:center;}.justify-between{justify-content:space-between;}.gap-2{gap:8px;}.gap-3{gap:12px;}.mb-3{margin-bottom:12px;}.mb-4{margin-bottom:20px;}.mt-3{margin-top:12px;}.mt-4{margin-top:20px;}.fw-bold{font-weight:700;}.text-muted{color:var(--text2);}
.form-input,.form-select,.form-textarea{width:100%;padding:9px 13px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--r2);color:var(--text);font-family:var(--sans);font-size:13px;outline:none;transition:border-color 0.15s;}
.form-input:focus,.form-select:focus{border-color:var(--orange);}
.form-select option{background:var(--bg2);}
.form-label{display:block;font-family:var(--mono);font-size:10px;color:var(--text3);letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;}
.form-group{margin-bottom:14px;}
.alert{padding:10px 14px;border-radius:var(--r2);font-size:12px;margin-bottom:14px;display:flex;align-items:center;gap:8px;}
.alert-warn{background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);color:#fcd34d;}
.alert-success{background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);color:#86efac;}
.alert-danger{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);color:#fca5a5;}
.tab-pills{display:flex;gap:6px;margin-bottom:20px;border-bottom:1px solid var(--border);padding-bottom:12px;}
.tab-pill{padding:6px 16px;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;color:var(--text2);border:1px solid transparent;transition:all 0.15s;}
.tab-pill:hover{color:var(--text);background:var(--surface2);}
.tab-pill.active{background:rgba(249,115,22,0.12);color:var(--orange);border-color:rgba(249,115,22,0.3);}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:200;display:flex;align-items:center;justify-content:center;}
.modal{background:var(--surface);border:1px solid var(--border2);border-radius:var(--r);padding:28px;width:100%;max-width:480px;position:relative;}
.modal-title{font-size:16px;font-weight:700;margin-bottom:16px;}
.search-row{display:flex;gap:10px;margin-bottom:16px;}
.search-row .form-input{flex:1;}
.empty-state{text-align:center;padding:40px 20px;color:var(--text3);}
.tag{display:inline-block;font-family:var(--mono);font-size:10px;padding:1px 7px;border-radius:10px;background:rgba(249,115,22,0.08);color:var(--orange);}
.progress{background:var(--bg2);border-radius:4px;height:5px;overflow:hidden;}
.progress-bar{height:100%;background:linear-gradient(90deg,var(--orange),var(--red));border-radius:4px;}
"""

def _admin_page(content: str, user: dict, title: str = "Admin", active: str = "overview") -> str:
    lang = _get_lang(user)
    nav = [
        ("overview",    "⚡", "Overview",    "/admin"),
        ("users",       "👥", "Users",       "/admin/users"),
        ("generations", "⚙", "Generations", "/admin/generations"),
        ("settings",    "⚙", "Settings",    "/admin/settings"),
        ("cache",       "🗑", "Cache",       "/admin/cache"),
        ("logs",        "📋", "Logs",        "/admin/logs"),
    ]
    nav_html = "".join(
        f'<a class="nav-item {"active" if active==k else ""}" href="{href}">'
        f'<span class="nav-icon">{icon}</span>{label}</a>'
        for k, icon, label, href in nav
    )
    init = user.get("name","A")[0].upper()
    return f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{escape_html(title)} — Admin Panel</title>
<style>{ADMIN_CSS}</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="sidebar-logo">
      <div class="logo-icon">🛡</div>
      <span class="logo-text">TrendPulse</span>
      <span class="logo-badge">ADMIN</span>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-section">Admin Panel</div>
      {nav_html}
      <div class="nav-section" style="margin-top:12px;">App</div>
      <a class="nav-item" href="/dashboard"><span class="nav-icon">←</span>Back to App</a>
    </nav>
    <div class="sidebar-footer">
      <div class="user-row">
        <div class="user-avatar">{init}</div>
        <div class="user-info">
          <div class="user-name">{escape_html(user["name"])}</div>
          <div class="user-plan">Administrator</div>
        </div>
        <a href="/logout" style="font-family:var(--mono);font-size:10px;color:var(--text3);text-decoration:none;padding:3px 7px;border:1px solid var(--border);border-radius:4px;">out</a>
      </div>
    </div>
  </aside>
  <main class="main">{content}</main>
</div>
<div id="toast-wrap" style="position:fixed;bottom:20px;right:20px;display:flex;flex-direction:column;gap:8px;z-index:9999;"></div>
<script>
function toast(msg,type='info'){{
  const icons={{success:'✓',error:'✕',info:'◈',warn:'⚠'}};
  const colors={{success:'rgba(34,197,94,0.3)',error:'rgba(239,68,68,0.3)',info:'rgba(249,115,22,0.3)',warn:'rgba(245,158,11,0.3)'}};
  const el=document.createElement('div');
  el.style.cssText='background:var(--surface);border:1px solid '+colors[type]+';border-radius:8px;padding:10px 14px;font-size:13px;min-width:220px;display:flex;align-items:center;gap:8px;';
  el.innerHTML='<span>'+icons[type]+'</span><span>'+msg+'</span>';
  document.getElementById('toast-wrap').appendChild(el);
  setTimeout(()=>el.remove(),3500);
}}
async function adminAction(url, method='POST', body=null, confirm_msg='') {{
  if(confirm_msg && !confirm(confirm_msg)) return;
  try {{
    const opts = {{method, headers:{{'Content-Type':'application/json'}}}};
    if(body) opts.body = JSON.stringify(body);
    const r = await fetch(url, opts);
    const d = await r.json();
    if(d.ok || d.success) {{ toast(d.msg || 'Done ✓', 'success'); setTimeout(()=>location.reload(), 800); }}
    else {{ toast(d.error || 'Failed', 'error'); }}
  }} catch(e) {{ toast('Request failed: '+e.message,'error'); }}
}}
</script>
</body></html>"""


# ── Overview ───────────────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_overview(request: Request, msg: str = ""):
    user, redir = _require_admin(request)
    if redir: return redir

    stats = get_system_stats()
    logs  = get_admin_logs(limit=10)

    msg_html = f'<div class="alert alert-success">✓ {escape_html(msg)}</div>' if msg else ""

    def stat(label, value, color="var(--text)", sub=""):
        return f'''<div class="stat-card">
          <div class="stat-label">{label}</div>
          <div class="stat-value" style="color:{color};">{value}</div>
          {f'<div class="stat-sub">{sub}</div>' if sub else ""}
        </div>'''

    gens_by_status = stats["by_status"]
    completed = gens_by_status.get("completed", 0)
    failed    = gens_by_status.get("failed", 0)
    running   = gens_by_status.get("running", 0) + gens_by_status.get("pending", 0)

    stats_html = f'''<div class="stats-grid">
      {stat("Total Users",    stats["total_users"],    "var(--text)",    f'+{stats["recent_signups"]} this week')}
      {stat("Generations",    stats["total_gens"],     "var(--accent)",  f'{stats["month_gens"]} this month')}
      {stat("Completed",      completed,               "var(--green)",   f'{failed} failed')}
      {stat("Active Jobs",    running,                 "var(--amber)",   "running now")}
      {stat("Banned Users",   stats["banned_users"],   "var(--red)",     f'{stats["admin_users"]} admins')}
    </div>'''

    # Plan distribution
    by_plan   = stats["by_plan"]
    plan_bars = ""
    total_u   = max(stats["total_users"], 1)
    for plan, cnt in sorted(by_plan.items(), key=lambda x: -x[1]):
        pct   = round(cnt / total_u * 100)
        color = {"free":"var(--text3)","starter":"var(--accent)","pro":"var(--green)","agency":"var(--orange)"}.get(plan,"var(--text2)")
        plan_bars += f'''<div style="margin-bottom:10px;">
          <div class="flex justify-between mb-3" style="margin-bottom:5px;">
            <span style="font-size:12px;font-weight:600;text-transform:capitalize;">{plan}</span>
            <span style="font-family:var(--mono);font-size:11px;color:var(--text3);">{cnt} users · {pct}%</span>
          </div>
          <div class="progress"><div class="progress-bar" style="width:{pct}%;background:{color};"></div></div>
        </div>'''

    # Recent admin logs
    log_rows = "".join(
        f'<tr><td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{l["created_at"][:16]}</td>'
        f'<td><span class="tag">{escape_html(l.get("admin_email","?"))}</span></td>'
        f'<td>{escape_html(l["action"])}</td>'
        f'<td style="color:var(--text2);font-size:12px;">{escape_html(l.get("details","")[:60])}</td></tr>'
        for l in logs
    ) or '<tr><td colspan="4" class="empty-state">No admin actions yet</td></tr>'

    content = f'''
    <div class="topbar">
      <div><div class="topbar-title">⚡ Admin Overview</div>
        <div class="topbar-sub">System health at a glance</div></div>
      <div class="flex gap-2">
        <a class="btn btn-ghost btn-sm" href="/admin/cache">🗑 Clear Cache</a>
        <a class="btn btn-primary btn-sm" href="/admin/users">👥 Manage Users</a>
      </div>
    </div>
    <div class="content">
      {msg_html}
      {stats_html}
      <div class="grid-2" style="gap:20px;">
        <div class="card">
          <div class="card-title">📊 Plan Distribution</div>
          {plan_bars or '<div class="empty-state">No users yet</div>'}
        </div>
        <div class="card">
          <div class="card-title">⚡ Generation Status</div>
          {_gen_status_chart(gens_by_status)}
        </div>
      </div>
      <div class="card mt-4" style="padding:0;overflow:hidden;">
        <div style="padding:14px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
          <div class="card-title" style="margin-bottom:0;">📋 Recent Admin Activity</div>
          <a class="btn btn-ghost btn-sm" href="/admin/logs">View all →</a>
        </div>
        <table><thead><tr><th>Time</th><th>Admin</th><th>Action</th><th>Details</th></tr></thead>
        <tbody>{log_rows}</tbody></table>
      </div>
    </div>'''
    return HTMLResponse(_admin_page(content, user, "Overview", "overview"))


def _gen_status_chart(by_status):
    statuses = [
        ("completed",        "var(--green)", "Completed"),
        ("failed",           "var(--red)",   "Failed"),
        ("running",          "var(--amber)", "Running"),
        ("pending",          "var(--text3)", "Pending"),
        ("scheduled",        "var(--accent)","Scheduled"),
        ("awaiting_approval","var(--accent2)","Awaiting"),
        ("cancelled",        "var(--text3)", "Cancelled"),
    ]
    total = max(sum(by_status.values()), 1)
    html  = ""
    for key, color, label in statuses:
        cnt = by_status.get(key, 0)
        if cnt == 0: continue
        pct = round(cnt / total * 100)
        html += f'''<div style="margin-bottom:8px;">
          <div class="flex justify-between" style="margin-bottom:4px;">
            <span style="font-size:12px;">{label}</span>
            <span style="font-family:var(--mono);font-size:11px;color:var(--text3);">{cnt} · {pct}%</span>
          </div>
          <div class="progress"><div class="progress-bar" style="width:{pct}%;background:{color};"></div></div>
        </div>'''
    return html or '<div class="empty-state">No generations yet</div>'


# ── Users ──────────────────────────────────────────────────────────────────────
@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request, search: str = "", plan: str = "",
                      status: str = "", msg: str = ""):
    user, redir = _require_admin(request)
    if redir: return redir

    users     = get_all_users(limit=500, search=search, plan_filter=plan, status_filter=status)
    msg_html  = f'<div class="alert alert-success mb-3">✓ {escape_html(msg)}</div>' if msg else ""
    err_html  = request.query_params.get("error","")
    err_html  = f'<div class="alert alert-danger mb-3">✕ {escape_html(err_html)}</div>' if err_html else ""

    def plan_badge(p):
        c = {"free":"badge-gray","starter":"badge-blue","pro":"badge-green","agency":"badge-orange"}.get(p,"badge-gray")
        return f'<span class="badge {c}">{p}</span>'

    def status_badges(u):
        out = []
        if u.get("is_admin"):   out.append('<span class="badge badge-orange">admin</span>')
        if u.get("is_banned"):  out.append('<span class="badge badge-red">banned</span>')
        if not u.get("is_active"): out.append('<span class="badge badge-gray">inactive</span>')
        return " ".join(out) if out else '<span class="badge badge-green">active</span>'

    rows = "".join(f'''<tr>
      <td>
        <div style="font-weight:600;font-size:13px;">{escape_html(u["name"])}</div>
        <div style="font-family:var(--mono);font-size:10px;color:var(--text3);">{escape_html(u["email"])}</div>
      </td>
      <td>{plan_badge(u.get("plan","free"))}</td>
      <td>{status_badges(u)}</td>
      <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{u.get("created_at","")[:10]}</td>
      <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{u.get("last_login","—")[:10] if u.get("last_login") else "—"}</td>
      <td>
        <div class="flex gap-2">
          <button class="btn btn-ghost btn-sm" onclick="openUserModal('{escape_js(u['id'])}','{escape_js(u['name'])}','{escape_js(u['email'])}','{u.get('plan','free')}',{1 if u.get('is_admin') else 0},{1 if u.get('is_banned') else 0})">Edit</button>
          <button class="btn btn-ghost btn-sm" onclick="loginAsUser('{escape_js(u['id'])}')" title="Impersonate">🔑</button>
        </div>
      </td>
    </tr>''' for u in users)

    plan_opts = "".join(f'<option value="{p}" {"selected" if p==plan else ""}>{p.title()}</option>'
                        for p in ["","free","starter","pro","agency"])
    status_opts = "".join(f'<option value="{s}" {"selected" if s==status else ""}>{l}</option>'
                          for s,l in [("","All"),("active","Active"),("banned","Banned"),("admin","Admin")])

    content = f'''
    <div class="topbar">
      <div><div class="topbar-title">👥 Users <span style="font-family:var(--mono);font-size:13px;color:var(--text3);">({len(users)})</span></div></div>
      <button class="btn btn-primary btn-sm" onclick="openCreateUserModal()">+ Create User</button>
    </div>
    <div class="content">
      {msg_html}{err_html}
      <form method="get" action="/admin/users" class="search-row mb-4">
        <input class="form-input" name="search" placeholder="Search name or email…" value="{escape_html(search)}"/>
        <select class="form-select" name="plan" style="width:130px;">{plan_opts}</select>
        <select class="form-select" name="status" style="width:130px;">{status_opts}</select>
        <button class="btn btn-ghost" type="submit">Search</button>
        <a class="btn btn-ghost" href="/admin/users">Reset</a>
      </form>
      <div class="table-wrap">
        <table><thead><tr><th>User</th><th>Plan</th><th>Status</th><th>Joined</th><th>Last Login</th><th></th></tr></thead>
        <tbody>{rows or '<tr><td colspan="6" class="empty-state">No users found</td></tr>'}</tbody></table>
      </div>
    </div>

    <!-- Edit User Modal -->
    <div id="user-modal" class="modal-overlay" style="display:none;" onclick="if(event.target===this)closeUserModal()">
      <div class="modal">
        <div class="modal-title">Edit User</div>
        <div class="form-group">
          <label class="form-label">Name</label>
          <div id="modal-name" style="font-size:14px;font-weight:600;"></div>
          <div id="modal-email" style="font-family:var(--mono);font-size:11px;color:var(--text3);margin-top:2px;"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Plan</label>
          <select class="form-select" id="modal-plan">
            <option value="free">Free</option>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="agency">Agency</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Permissions</label>
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;">
            <input type="checkbox" id="modal-is-admin" style="accent-color:var(--orange);width:15px;height:15px;"/>
            Grant admin access
          </label>
        </div>
        <div id="modal-ban-section" class="form-group">
          <label class="form-label">Ban Reason <span style="color:var(--text3);font-weight:400;">(leave blank to unban)</span></label>
          <input class="form-input" id="modal-ban-reason" placeholder="Reason for ban…"/>
        </div>
        <div class="flex gap-2 mt-3">
          <button class="btn btn-primary" onclick="saveUser()">Save Changes</button>
          <button class="btn btn-danger btn-sm" onclick="deleteUser()" title="Permanently delete user and all data">🗑 Delete</button>
          <button class="btn btn-ghost" onclick="closeUserModal()">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Create User Modal -->
    <div id="create-modal" class="modal-overlay" style="display:none;" onclick="if(event.target===this)closeCreateUserModal()">
      <div class="modal">
        <div class="modal-title">Create User</div>
        <div class="form-group"><label class="form-label">Name</label><input class="form-input" id="cu-name" placeholder="Full name"/></div>
        <div class="form-group"><label class="form-label">Email</label><input class="form-input" id="cu-email" type="email" placeholder="user@example.com"/></div>
        <div class="form-group"><label class="form-label">Password</label><input class="form-input" id="cu-pass" type="password" placeholder="Min 8 chars"/></div>
        <div class="form-group"><label class="form-label">Plan</label>
          <select class="form-select" id="cu-plan">
            <option value="free">Free</option><option value="starter">Starter</option>
            <option value="pro">Pro</option><option value="agency">Agency</option>
          </select></div>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;margin-bottom:14px;">
          <input type="checkbox" id="cu-admin" style="accent-color:var(--orange);width:15px;height:15px;"/> Grant admin access</label>
        <div class="flex gap-2">
          <button class="btn btn-primary" onclick="createUser()">Create User</button>
          <button class="btn btn-ghost" onclick="closeCreateUserModal()">Cancel</button>
        </div>
      </div>
    </div>

    <script>
    let _uid = '';
    function openUserModal(id,name,email,plan,isAdmin,isBanned){{
      _uid=id;
      document.getElementById('modal-name').textContent=name;
      document.getElementById('modal-email').textContent=email;
      document.getElementById('modal-plan').value=plan;
      document.getElementById('modal-is-admin').checked=isAdmin===1||isAdmin===true;
      document.getElementById('modal-ban-reason').value='';
      document.getElementById('user-modal').style.display='flex';
    }}
    function closeUserModal(){{ document.getElementById('user-modal').style.display='none'; }}
    function openCreateUserModal(){{ document.getElementById('create-modal').style.display='flex'; }}
    function closeCreateUserModal(){{ document.getElementById('create-modal').style.display='none'; }}
    async function saveUser(){{
      const plan=document.getElementById('modal-plan').value;
      const is_admin=document.getElementById('modal-is-admin').checked;
      const ban_reason=document.getElementById('modal-ban-reason').value.trim();
      await adminAction('/admin/api/user/'+_uid, 'POST', {{plan,is_admin,ban_reason}});
    }}
    async function deleteUser(){{
      await adminAction('/admin/api/user/'+_uid+'/delete','POST',null,'Permanently delete this user and ALL their data? This cannot be undone.');
    }}
    async function loginAsUser(uid){{
      if(!confirm('Login as this user? You will be redirected to their dashboard.')) return;
      const r = await fetch('/admin/api/impersonate/'+uid, {{method:'POST'}});
      const d = await r.json();
      if(d.ok) window.location='/dashboard'; else toast(d.error||'Failed','error');
    }}
    async function createUser(){{
      const name=document.getElementById('cu-name').value.trim();
      const email=document.getElementById('cu-email').value.trim();
      const password=document.getElementById('cu-pass').value;
      const plan=document.getElementById('cu-plan').value;
      const is_admin=document.getElementById('cu-admin').checked;
      if(!name||!email||!password){{toast('Fill all fields','warn');return;}}
      await adminAction('/admin/api/user/create','POST',{{name,email,password,plan,is_admin}});
    }}
    </script>'''
    return HTMLResponse(_admin_page(content, user, "Users", "users"))


# ── Generations ────────────────────────────────────────────────────────────────
@router.get("/generations", response_class=HTMLResponse)
async def admin_generations(request: Request, status: str = "", user_id: str = ""):
    user, redir = _require_admin(request)
    if redir: return redir

    gens = get_all_generations_admin(limit=200, status_filter=status, user_id=user_id)

    sb = {"completed":"badge-green","running":"badge-amber","generating_media":"badge-amber",
          "awaiting_approval":"badge-amber","pending":"badge-gray","failed":"badge-red",
          "scheduled":"badge-blue","cancelled":"badge-gray"}

    status_opts = "".join(
        f'<option value="{s}" {"selected" if s==status else ""}>{l}</option>'
        for s,l in [("","All"),("completed","Completed"),("running","Running"),
                    ("failed","Failed"),("scheduled","Scheduled"),("pending","Pending"),("cancelled","Cancelled")]
    )

    rows = "".join(f'''<tr>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600;">{escape_html(g["topic"])}</td>
      <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{escape_html(g.get("user_email","?"))}</td>
      <td>{"🎬" if g["content_type"]=="video" else "📸"} {g["content_type"]}</td>
      <td><span class="badge {sb.get(g["status"],"badge-gray")}">{g["status"].replace("_"," ")}</span>
          {"<span class='badge badge-amber' style='margin-left:4px;'>fallback</span>" if g.get("fallback_used") else ""}</td>
      <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{g["created_at"][:16]}</td>
      <td>
        <div class="flex gap-2">
          <a class="btn btn-ghost btn-sm" href="/admin/generations/{g["id"]}">View</a>
          {f'<button class="btn btn-danger btn-sm" onclick="adminAction(\'/admin/api/generation/{g["id"]}/cancel\',\'POST\',null,\'Cancel this generation?\')">Cancel</button>' if g["status"] in ("running","scheduled","pending") else ""}
          <button class="btn btn-danger btn-sm" onclick="adminAction('/admin/api/generation/{g["id"]}/delete','POST',null,'Delete generation and all media files?')">🗑</button>
        </div>
      </td>
    </tr>''' for g in gens)

    content = f'''
    <div class="topbar">
      <div><div class="topbar-title">⚙ Generations <span style="font-family:var(--mono);font-size:13px;color:var(--text3);">({len(gens)})</span></div></div>
    </div>
    <div class="content">
      <form method="get" action="/admin/generations" class="search-row mb-4">
        <select class="form-select" name="status" style="width:160px;">{status_opts}</select>
        <input class="form-input" name="user_id" placeholder="Filter by user ID…" value="{escape_html(user_id)}"/>
        <button class="btn btn-ghost" type="submit">Filter</button>
        <a class="btn btn-ghost" href="/admin/generations">Reset</a>
      </form>
      <div class="table-wrap">
        <table><thead><tr><th>Topic</th><th>User</th><th>Type</th><th>Status</th><th>Created</th><th></th></tr></thead>
        <tbody>{rows or '<tr><td colspan="6" class="empty-state">No generations found</td></tr>'}</tbody></table>
      </div>
    </div>'''
    return HTMLResponse(_admin_page(content, user, "Generations", "generations"))


@router.get("/generations/{gid}", response_class=HTMLResponse)
async def admin_generation_detail(request: Request, gid: str):
    user, redir = _require_admin(request)
    if redir: return redir

    gen = get_generation_admin(gid)
    if not gen:
        return RedirectResponse("/admin/generations")

    cfg    = gen.get("config", {})
    result = gen.get("result", {}) or {}
    ideas  = result.get("ideas", [])

    ideas_html = ""
    for i, idea in enumerate(ideas[:10]):
        hook = idea.get("hook","") if not isinstance(idea.get("hook"),dict) else idea["hook"].get("text","")
        ideas_html += f'<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:12px;"><span style="color:var(--orange);">#{i+1}</span> {escape_html(str(hook)[:120])}</div>'

    cfg_json  = json.dumps(cfg, indent=2, ensure_ascii=False)
    err_html  = f'<div class="alert alert-danger">{escape_html(gen.get("error",""))}</div>' if gen.get("error") else ""

    content = f'''
    <div class="topbar">
      <div><div class="topbar-title">Generation Detail</div>
        <div class="topbar-sub" style="font-family:var(--mono);font-size:10px;">{gid}</div></div>
      <div class="flex gap-2">
        <a class="btn btn-ghost btn-sm" href="/admin/generations">← Back</a>
        <a class="btn btn-ghost btn-sm" href="/result/{gid}" target="_blank">View as user ↗</a>
      </div>
    </div>
    <div class="content">
      {err_html}
      <div class="grid-2 mb-4">
        <div class="card">
          <div class="card-title">Details</div>
          {"".join(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;"><span style="color:var(--text2);">{k}</span><span style="font-weight:600;">{escape_html(str(v))}</span></div>' for k,v in [("Topic",gen["topic"]),("Type",gen["content_type"]),("Status",gen["status"]),("Language",gen["language"]),("User ID",gen.get("user_id","")),("Created",gen.get("created_at","")[:16]),("Fallback","Yes" if gen.get("fallback_used") else "No")])}
        </div>
        <div class="card">
          <div class="card-title">Ideas ({len(ideas)})</div>
          {ideas_html or '<div class="empty-state" style="padding:20px;">No ideas</div>'}
        </div>
      </div>
      <div class="card">
        <div class="card-title">Config JSON</div>
        <pre style="font-family:var(--mono);font-size:11px;color:var(--text2);overflow-x:auto;white-space:pre-wrap;max-height:300px;">{escape_html(cfg_json)}</pre>
      </div>
    </div>'''
    return HTMLResponse(_admin_page(content, user, "Generation Detail", "generations"))


# ── Settings ───────────────────────────────────────────────────────────────────
@router.get("/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request, msg: str = ""):
    user, redir = _require_admin(request)
    if redir: return redir

    settings = get_all_system_settings()
    msg_html = f'<div class="alert alert-success mb-3">✓ {escape_html(msg)}</div>' if msg else ""

    rows = "".join(f'''<tr>
      <td style="font-family:var(--mono);font-size:12px;">{escape_html(s["key"])}</td>
      <td><input class="form-input" style="font-family:var(--mono);font-size:11px;" name="val_{escape_html(s['key'])}" value="{escape_html(s['value'])}" form="settings-form"/></td>
      <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{s.get("updated_at","")[:16]}</td>
    </tr>''' for s in settings)

    content = f'''
    <div class="topbar">
      <div><div class="topbar-title">⚙ System Settings</div></div>
      <div class="flex gap-2">
        <button class="btn btn-primary" form="settings-form" type="submit">Save All Settings</button>
        <button class="btn btn-ghost btn-sm" onclick="openAddSetting()">+ Add Setting</button>
      </div>
    </div>
    <div class="content">
      {msg_html}
      <div class="card mb-4">
        <div class="card-title">⚠ Quick Admin Controls</div>
        <div class="flex gap-3" style="flex-wrap:wrap;">
          <button class="btn btn-danger btn-sm" onclick="adminAction('/admin/api/clear-all-cache','POST',null,'Clear all caches? This will force fresh data fetches on next run.')">🗑 Clear All Caches</button>
          <button class="btn btn-amber btn-sm" onclick="adminAction('/admin/api/cancel-all-running','POST',null,'Cancel all currently running generations?')">⏹ Cancel All Running</button>
          <a class="btn btn-ghost btn-sm" href="/admin/settings?msg=refreshed">↻ Refresh Page</a>
        </div>
      </div>
      <div class="table-wrap">
        <form id="settings-form" method="post" action="/admin/settings/save">
          <table><thead><tr><th>Key</th><th>Value</th><th>Updated</th></tr></thead>
          <tbody>{rows or '<tr><td colspan="3" class="empty-state">No settings stored yet</td></tr>'}</tbody>
          </table>
        </form>
      </div>
    </div>

    <div id="add-modal" class="modal-overlay" style="display:none;" onclick="if(event.target===this)closeAddSetting()">
      <div class="modal">
        <div class="modal-title">Add System Setting</div>
        <div class="form-group"><label class="form-label">Key</label><input class="form-input" id="new-key" placeholder="e.g. maintenance_mode"/></div>
        <div class="form-group"><label class="form-label">Value</label><input class="form-input" id="new-val" placeholder="true / false / any value"/></div>
        <div class="flex gap-2">
          <button class="btn btn-primary" onclick="addSetting()">Add</button>
          <button class="btn btn-ghost" onclick="closeAddSetting()">Cancel</button>
        </div>
      </div>
    </div>
    <script>
    function openAddSetting(){{ document.getElementById('add-modal').style.display='flex'; }}
    function closeAddSetting(){{ document.getElementById('add-modal').style.display='none'; }}
    async function addSetting(){{
      const key=document.getElementById('new-key').value.trim();
      const val=document.getElementById('new-val').value.trim();
      if(!key){{toast('Key required','warn');return;}}
      await adminAction('/admin/api/setting/set','POST',{{key,value:val}});
    }}
    </script>'''
    return HTMLResponse(_admin_page(content, user, "Settings", "settings"))


@router.post("/settings/save", response_class=HTMLResponse)
async def admin_settings_save(request: Request):
    user, redir = _require_admin(request)
    if redir: return redir

    form = await request.form()
    saved = 0
    for key, val in form.items():
        if key.startswith("val_"):
            setting_key = key[4:]
            set_system_setting(setting_key, str(val))
            saved += 1

    log_admin_action(user["id"], "settings_save", "system", "", f"Saved {saved} settings")
    return RedirectResponse(f"/admin/settings?msg=Saved+{saved}+settings", status_code=303)


# ── Cache ──────────────────────────────────────────────────────────────────────
@router.get("/cache", response_class=HTMLResponse)
async def admin_cache_page(request: Request, msg: str = ""):
    user, redir = _require_admin(request)
    if redir: return redir

    msg_html = f'<div class="alert alert-success mb-3">✓ {escape_html(msg)}</div>' if msg else ""

    _project_root = Path(__file__).resolve().parent.parent
    cache_files   = [
        (_project_root / "data" / "processed" / "trend_cache.json",    "Trend cache",    "24h TTL — trend intelligence"),
        (_project_root / "data" / "processed" / "embedding_cache.pkl", "Embedding cache","Sentence transformer embeddings"),
    ]

    cache_rows = ""
    for path, label, desc in cache_files:
        exists  = path.exists()
        size    = f"{path.stat().st_size / 1024:.1f} KB" if exists else "—"
        mtime   = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if exists else "—"
        status  = '<span class="badge badge-green">exists</span>' if exists else '<span class="badge badge-gray">not found</span>'
        cache_rows += f'''<tr>
          <td style="font-weight:600;">{label}</td>
          <td style="font-size:12px;color:var(--text2);">{desc}</td>
          <td>{status}</td>
          <td style="font-family:var(--mono);font-size:11px;">{size}</td>
          <td style="font-family:var(--mono);font-size:11px;color:var(--text3);">{mtime}</td>
          <td>{"<button class='btn btn-danger btn-sm' onclick='clearCache(\""+str(path)+"\")'>Clear</button>" if exists else "<span style='color:var(--text3);font-size:12px;'>—</span>"}</td>
        </tr>'''

    content = f'''
    <div class="topbar">
      <div><div class="topbar-title">🗑 Cache Management</div></div>
      <button class="btn btn-danger btn-sm" onclick="adminAction('/admin/api/clear-all-cache','POST',null,'Clear ALL caches?')">Clear All</button>
    </div>
    <div class="content">
      {msg_html}
      <div class="table-wrap">
        <table><thead><tr><th>Cache</th><th>Description</th><th>Status</th><th>Size</th><th>Last Modified</th><th></th></tr></thead>
        <tbody>{cache_rows}</tbody></table>
      </div>
    </div>
    <script>
    async function clearCache(path){{
      await adminAction('/admin/api/clear-cache','POST',{{path}},'Clear this cache file?');
    }}
    </script>'''
    return HTMLResponse(_admin_page(content, user, "Cache", "cache"))


# ── Logs ───────────────────────────────────────────────────────────────────────
@router.get("/logs", response_class=HTMLResponse)
async def admin_logs_page(request: Request):
    user, redir = _require_admin(request)
    if redir: return redir

    logs = get_admin_logs(limit=300)

    rows = "".join(f'''<tr>
      <td style="font-family:var(--mono);font-size:10px;color:var(--text3);">{l["created_at"][:16]}</td>
      <td><span class="tag">{escape_html(l.get("admin_email","?"))}</span></td>
      <td style="font-weight:600;font-size:12px;">{escape_html(l["action"])}</td>
      <td style="font-family:var(--mono);font-size:10px;color:var(--text2);">{escape_html(l.get("target_type",""))}</td>
      <td style="font-size:12px;color:var(--text2);">{escape_html(l.get("details","")[:100])}</td>
    </tr>''' for l in logs)

    content = f'''
    <div class="topbar">
      <div><div class="topbar-title">📋 Admin Logs <span style="font-family:var(--mono);font-size:13px;color:var(--text3);">({len(logs)})</span></div></div>
    </div>
    <div class="content">
      <div class="table-wrap">
        <table><thead><tr><th>Time</th><th>Admin</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
        <tbody>{rows or '<tr><td colspan="5" class="empty-state">No logs yet</td></tr>'}</tbody></table>
      </div>
    </div>'''
    return HTMLResponse(_admin_page(content, user, "Logs", "logs"))


# ── JSON API endpoints ─────────────────────────────────────────────────────────
@router.post("/api/user/{uid}")
async def api_edit_user(request: Request, uid: str):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    plan       = body.get("plan", "")
    is_admin   = body.get("is_admin", False)
    ban_reason = body.get("ban_reason", "").strip()

    if plan in PLAN_QUOTAS:
        update_user_plan(uid, plan)
        log_admin_action(admin["id"], "change_plan", "user", uid, f"→ {plan}")

    set_user_admin(uid, bool(is_admin))
    log_admin_action(admin["id"], "set_admin" if is_admin else "remove_admin", "user", uid)

    if ban_reason:
        ban_user(uid, ban_reason)
        log_admin_action(admin["id"], "ban_user", "user", uid, ban_reason)
    else:
        unban_user(uid)

    return JSONResponse({"ok": True, "msg": "User updated"})


@router.post("/api/user/{uid}/delete")
async def api_delete_user(request: Request, uid: str):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if uid == admin["id"]:
        return JSONResponse({"error": "Cannot delete yourself"}, status_code=400)
    delete_user_admin(uid)
    log_admin_action(admin["id"], "delete_user", "user", uid, "Hard delete")
    return JSONResponse({"ok": True, "msg": "User deleted"})


@router.post("/api/user/create")
async def api_create_user(request: Request):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    from db import get_user_by_email, create_user as _create_user
    email    = body.get("email","").strip().lower()
    name     = body.get("name","").strip()
    password = body.get("password","")
    plan     = body.get("plan","free")
    is_admin_flag = body.get("is_admin", False)

    if not email or not name or len(password) < 8:
        return JSONResponse({"error": "Name, email and password (min 8) required"}, status_code=400)
    if get_user_by_email(email):
        return JSONResponse({"error": "Email already registered"}, status_code=400)

    new_user = _create_user(email, name, password, is_admin=is_admin_flag)
    update_user_plan(new_user["id"], plan)
    log_admin_action(admin["id"], "create_user", "user", new_user["id"], f"{email} / {plan}")
    return JSONResponse({"ok": True, "msg": f"User {email} created"})


@router.post("/api/impersonate/{uid}")
async def api_impersonate(request: Request, uid: str):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from db import get_user_by_id
    from auth import create_token
    target = get_user_by_id(uid)
    if not target:
        return JSONResponse({"error": "User not found"}, status_code=404)
    token = create_token(uid)
    log_admin_action(admin["id"], "impersonate", "user", uid, target.get("email",""))
    response = JSONResponse({"ok": True})
    from auth import TOKEN_EXPIRE
    response.set_cookie("sm_token", token, httponly=True, samesite="lax", max_age=TOKEN_EXPIRE*60)
    return response


@router.post("/api/generation/{gid}/cancel")
async def api_cancel_generation(request: Request, gid: str):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    with get_conn() as conn:
        conn.execute(
            "UPDATE generations SET status='cancelled' WHERE id=? AND status NOT IN ('completed','failed')",
            (gid,)
        )
    log_admin_action(admin["id"], "cancel_generation", "generation", gid)
    return JSONResponse({"ok": True, "msg": "Generation cancelled"})


@router.post("/api/generation/{gid}/delete")
async def api_delete_generation(request: Request, gid: str):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    with get_conn() as conn:
        row = conn.execute("SELECT user_id FROM generations WHERE id=?", (gid,)).fetchone()
    if row:
        uid     = row["user_id"]
        out_dir = OUTPUT_ROOT / uid / gid
        import shutil
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
    with get_conn() as conn:
        conn.execute("DELETE FROM usage       WHERE gen_id=?", (gid,))
        conn.execute("DELETE FROM generations WHERE id=?",     (gid,))
    log_admin_action(admin["id"], "delete_generation", "generation", gid)
    return JSONResponse({"ok": True, "msg": "Generation deleted"})


@router.post("/api/clear-all-cache")
async def api_clear_all_cache(request: Request):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)

    _project_root = Path(__file__).resolve().parent.parent
    cleared = []
    for fname in ["trend_cache.json", "embedding_cache.pkl"]:
        p = _project_root / "data" / "processed" / fname
        if p.exists():
            p.unlink()
            cleared.append(fname)

    log_admin_action(admin["id"], "clear_all_cache", "system", "", f"Cleared: {', '.join(cleared)}")
    return JSONResponse({"ok": True, "msg": f"Cleared {len(cleared)} cache file(s)"})


@router.post("/api/clear-cache")
async def api_clear_specific_cache(request: Request):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    path = Path(body.get("path", ""))
    # Security: only allow deleting files inside data/processed
    _project_root = Path(__file__).resolve().parent.parent
    allowed_dir   = _project_root / "data" / "processed"
    try:
        path.resolve().relative_to(allowed_dir.resolve())
    except ValueError:
        return JSONResponse({"error": "Path not allowed"}, status_code=403)

    if path.exists():
        path.unlink()
    log_admin_action(admin["id"], "clear_cache", "system", "", str(path.name))
    return JSONResponse({"ok": True, "msg": f"Cleared {path.name}"})


@router.post("/api/cancel-all-running")
async def api_cancel_all_running(request: Request):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    with get_conn() as conn:
        conn.execute(
            "UPDATE generations SET status='cancelled' WHERE status IN ('running','pending')"
        )
    log_admin_action(admin["id"], "cancel_all_running", "system")
    return JSONResponse({"ok": True, "msg": "All running/pending generations cancelled"})


@router.post("/api/setting/set")
async def api_set_setting(request: Request):
    admin, redir = _require_admin(request)
    if redir: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    key = str(body.get("key","")).strip()
    val = str(body.get("value",""))
    if not key:
        return JSONResponse({"error": "Key required"}, status_code=400)
    set_system_setting(key, val)
    log_admin_action(admin["id"], "set_setting", "system", key, f"→ {val[:50]}")
    return JSONResponse({"ok": True, "msg": f"Setting '{key}' saved"})
