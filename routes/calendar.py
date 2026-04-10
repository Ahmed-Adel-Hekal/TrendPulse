"""routes/calendar.py — Interactive calendar. Fixed + Generate-from-calendar feature."""
from __future__ import annotations
import datetime
import calendar as _cal_mod
import json
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import get_current_user
from db import (get_calendar_items, update_calendar_item_status,
                delete_calendar_item, get_user_settings, get_conn,
                safe_json_loads)
from core.i18n import normalize_lang, t as _t
import ui

router = APIRouter()

PLAT_ICONS = {
    "Instagram": "📸", "TikTok": "🎬", "LinkedIn": "💼",
    "Twitter/X": "🐦", "Facebook": "👥",
}
STATUS_COLORS = {
    "scheduled": "var(--accent)",
    "completed": "var(--green)",
    "cancelled": "var(--text3)",
    "failed":    "var(--red)",
}


def _h(s):
    """HTML escape."""
    if not s: return ""
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace('"',"&quot;").replace("'","&#x27;"))


def _j(s):
    """JS string escape — safe for single-quoted JS strings."""
    if not s: return ""
    return (str(s).replace("\\","\\\\").replace("'","\\'").replace('"','\\"')
            .replace("\n","\\n").replace("\r","\\r")
            .replace("<","\\x3C").replace(">","\\x3E").replace("&","\\x26"))


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request, year: int = 0, month: int = 0):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    try:
        s    = get_user_settings(user["id"])
        lang = normalize_lang(s.get("ui_language", "en"))

        now   = datetime.date.today()
        year  = year  or now.year
        month = month or now.month

        items = get_calendar_items(user["id"], year, month)

        by_date: dict = {}
        for item in items:
            by_date.setdefault(item["publish_date"], []).append(item)

        cal      = _cal_mod.monthcalendar(year, month)
        month_nm = datetime.date(year, month, 1).strftime("%B %Y")

        prev_m = month - 1 if month > 1 else 12
        prev_y = year      if month > 1 else year - 1
        next_m = month + 1 if month < 12 else 1
        next_y = year      if month < 12 else year + 1

        day_headers = "".join(
            '<th style="font-family:var(--mono);font-size:9px;letter-spacing:1.5px;'
            'text-align:center;padding:10px;color:var(--text3);">' + d + "</th>"
            for d in ["MON","TUE","WED","THU","FRI","SAT","SUN"]
        )

        weeks_html = ""
        for week in cal:
            cells = ""
            for day in week:
                if day == 0:
                    cells += '<td class="cal-cell empty"></td>'
                    continue

                date_str  = "{}-{:02d}-{:02d}".format(year, month, day)
                is_today  = date_str == now.isoformat()
                day_items = by_date.get(date_str, [])
                today_cls = " today" if is_today else ""

                events_html = ""
                for it in day_items[:3]:
                    color = STATUS_COLORS.get(it["status"], "var(--accent)")
                    icon  = PLAT_ICONS.get(it["platform"], "📱")

                    # Build the idea JSON for generate redirect
                    idea     = it.get("idea") or {}
                    topic    = idea.get("title") or idea.get("hook") or it.get("title","")
                    platform = it.get("platform","Instagram")
                    ct       = it.get("content_type","static")

                    # Encode generate URL params
                    gen_params = urllib.parse.urlencode({
                        "topic":        topic[:200],
                        "platform":     platform,
                        "content_type": ct,
                        "from_calendar":"1",
                        "cal_id":       it["id"],
                    })

                    events_html += (
                        '<div class="cal-event ' + it["status"] + '" '
                        'style="border-left-color:' + color + ';" '
                        'onclick="calEventClick(event,'
                        "'" + _j(it["id"])    + "',"
                        "'" + _j(it.get("title",""))    + "',"
                        "'" + _j(platform)    + "',"
                        "'" + _j(date_str)    + "',"
                        "'" + _j(it.get("publish_time","09:00")) + "',"
                        "'" + _j(it["status"])+ "',"
                        "'" + _j(ct)          + "',"
                        "'" + _j(gen_params)  + "'"
                        ')" '
                        'title="' + _h(it.get("title","")) + ' — click to manage">'
                        + icon + " " + _h(it.get("title","")[:22]) +
                        "</div>"
                    )

                if len(day_items) > 3:
                    events_html += '<div class="cal-more">+' + str(len(day_items)-3) + " more</div>"

                cells += (
                    '<td class="cal-cell' + today_cls + '" data-date="' + date_str + '">'
                    '<div class="cal-day-num">' + str(day) + "</div>"
                    + events_html +
                    "</td>"
                )
            weeks_html += "<tr>" + cells + "</tr>"

        # Upcoming list
        all_scheduled = sorted(
            [it for dits in by_date.values() for it in dits if it["status"] == "scheduled"],
            key=lambda x: (x["publish_date"], x.get("publish_time","09:00"))
        )[:10]

        upcoming_rows = ""
        for it in all_scheduled:
            icon  = PLAT_ICONS.get(it["platform"],"📱")
            ct    = it.get("content_type","static")
            idea  = it.get("idea") or {}
            topic = idea.get("title") or idea.get("hook") or it.get("title","")
            gen_params = urllib.parse.urlencode({
                "topic":        topic[:200],
                "platform":     it["platform"],
                "content_type": ct,
                "from_calendar":"1",
                "cal_id":       it["id"],
            })
            upcoming_rows += (
                "<tr>"
                "<td>" + icon + " " + _h(it["platform"]) + "</td>"
                '<td style="font-weight:500;">' + _h(it.get("title","")[:50]) + "</td>"
                '<td style="font-family:var(--mono);font-size:10px;color:var(--text3);">'
                + it["publish_date"] + " " + it.get("publish_time","09:00") + "</td>"
                '<td><span class="badge badge-amber" style="font-size:9px;">' + _h(ct) + "</span></td>"
                "<td>"
                '<a class="btn btn-primary btn-sm" href="/generate?' + _h(gen_params) + '">Generate ✦</a>'
                ' <button class="btn btn-danger btn-sm" onclick="cancelItem(\'' + _j(it["id"]) + '\')">Cancel</button>'
                "</td>"
                "</tr>"
            )

        if not upcoming_rows:
            upcoming_rows = (
                '<tr><td colspan="5" style="text-align:center;color:var(--text3);padding:28px;">'
                "No scheduled posts this month</td></tr>"
            )

        total_items     = len(items)
        scheduled_count = sum(1 for it in items if it["status"] == "scheduled")
        completed_count = sum(1 for it in items if it["status"] == "completed")

        content = (
            '<div class="topbar">'
            '<div>'
            '<div class="topbar-title">' + _h(_t(lang,"nav.calendar")) + "</div>"
            '<div class="topbar-sub">' + _h(month_nm) + " · " + str(total_items) + " posts</div>"
            "</div>"
            '<div class="flex gap-2">'
            '<a class="btn btn-ghost btn-sm" href="/calendar?year=' + str(prev_y) + "&month=" + str(prev_m) + '">&larr;</a>'
            '<a class="btn btn-ghost btn-sm" href="/calendar?year=' + str(now.year) + "&month=" + str(now.month) + '">Today</a>'
            '<a class="btn btn-ghost btn-sm" href="/calendar?year=' + str(next_y) + "&month=" + str(next_m) + '">&rarr;</a>'
            '<a class="btn btn-primary btn-sm" href="/strategy">+ Strategy</a>'
            "</div></div>"

            '<div class="content">'

            '<div class="grid-3 mb-4" style="gap:12px;">'
            '<div class="stat-card" style="padding:14px;">'
            '<div class="stat-label">Total Posts</div>'
            '<div class="stat-value" style="font-size:24px;">' + str(total_items) + "</div>"
            "</div>"
            '<div class="stat-card" style="padding:14px;">'
            '<div class="stat-label">Scheduled</div>'
            '<div class="stat-value" style="font-size:24px;color:var(--accent);">' + str(scheduled_count) + "</div>"
            "</div>"
            '<div class="stat-card" style="padding:14px;">'
            '<div class="stat-label">Completed</div>'
            '<div class="stat-value" style="font-size:24px;color:var(--green);">' + str(completed_count) + "</div>"
            "</div>"
            "</div>"

            '<div class="card mb-4" style="padding:0;overflow:hidden;">'
            '<div class="cal-header">'
            '<div class="cal-month">' + _h(month_nm) + "</div>"
            '<div class="cal-nav">'
            '<a class="btn btn-ghost btn-sm" href="/calendar?year=' + str(prev_y) + "&month=" + str(prev_m) + '">&larr;</a>'
            '<a class="btn btn-ghost btn-sm" href="/calendar?year=' + str(now.year) + "&month=" + str(now.month) + '">Today</a>'
            '<a class="btn btn-ghost btn-sm" href="/calendar?year=' + str(next_y) + "&month=" + str(next_m) + '">&rarr;</a>'
            "</div></div>"
            '<table class="cal-grid"><thead><tr>' + day_headers + "</tr></thead>"
            "<tbody>" + weeks_html + "</tbody></table>"
            "</div>"

            '<div class="card" style="padding:0;overflow:hidden;">'
            '<div style="padding:14px 20px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">'
            '<div style="font-size:12px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px;">Upcoming — click Generate to create content</div>'
            "</div>"
            "<table><thead><tr><th>Platform</th><th>Post</th><th>Date / Time</th><th>Type</th><th></th></tr></thead>"
            "<tbody>" + upcoming_rows + "</tbody></table>"
            "</div></div>"

            # Popover
            '<div id="cal-popover" style="display:none;position:fixed;z-index:300;'
            'background:var(--surface2);border:1px solid var(--border2);border-radius:var(--r);'
            'padding:18px;min-width:260px;max-width:320px;box-shadow:var(--shadow-lg);" '
            'onclick="event.stopPropagation();">'
            '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">'
            '<div id="pop-title" style="font-weight:600;font-size:14px;flex:1;margin-right:8px;"></div>'
            '<button onclick="closePopover()" style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:18px;line-height:1;padding:0;">&times;</button>'
            "</div>"
            '<div id="pop-meta" style="font-family:var(--mono);font-size:10px;color:var(--text3);margin-bottom:14px;"></div>'
            '<div id="pop-actions" style="display:flex;flex-direction:column;gap:8px;"></div>'
            "</div>"

            # Reschedule modal
            '<div id="reschedule-modal" style="display:none;position:fixed;inset:0;'
            'background:rgba(0,0,0,0.75);z-index:400;align-items:center;justify-content:center;">'
            '<div class="card" style="max-width:360px;width:calc(100% - 40px);position:relative;">'
            '<div style="font-size:15px;font-weight:600;margin-bottom:18px;">Reschedule Post</div>'
            '<div class="form-group"><label class="form-label">New Date</label>'
            '<input class="form-input" type="date" id="reschedule-date"/></div>'
            '<div class="form-group"><label class="form-label">New Time</label>'
            '<input class="form-input" type="time" id="reschedule-time" value="09:00"/></div>'
            '<div class="flex gap-2">'
            '<button class="btn btn-primary" onclick="confirmReschedule()">Reschedule</button>'
            '<button class="btn btn-ghost" onclick="closeReschedule()">Cancel</button>'
            "</div></div></div>"

            "<script>" + _CALENDAR_JS + "</script>"
        )

        return HTMLResponse(ui._page(content, user, _t(lang,"nav.calendar"), "calendar", lang))

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return HTMLResponse(
            "<h2 style='font-family:monospace;padding:40px;color:#e00;'>Calendar error: " + str(exc) + "</h2>",
            status_code=500
        )


_CALENDAR_JS = """
var _currentItemId = null;
var _currentGenParams = null;

function calEventClick(evt, id, title, platform, date, time, status, ct, genParams) {
  evt.stopPropagation();
  _currentItemId  = id;
  _currentGenParams = genParams;

  document.getElementById('pop-title').textContent = title || 'Untitled';

  var icons = {Instagram:'📸', TikTok:'🎬', LinkedIn:'💼', 'Twitter/X':'🐦', Facebook:'👥'};
  document.getElementById('pop-meta').textContent =
    (icons[platform] || '📱') + ' ' + platform + '  ·  ' + date + ' ' + time + '  ·  ' + ct;

  var acts = document.getElementById('pop-actions');
  acts.innerHTML = '';

  // Primary: generate content from this item
  acts.innerHTML +=
    '<a class="btn btn-primary" href="/generate?' + (genParams || '') + '" style="text-align:center;justify-content:center;">'
    + '✦ Generate Content</a>';

  if (status === 'scheduled') {
    acts.innerHTML +=
      '<button class="btn btn-green btn-sm" onclick="markCompleted(\'' + id + '\')">✓ Mark completed</button>' +
      '<button class="btn btn-ghost btn-sm" onclick="openReschedule(\'' + id + "','" + date + "','" + time + '\')">📅 Reschedule</button>' +
      '<button class="btn btn-danger btn-sm" onclick="cancelItem(\'' + id + '\')">✕ Cancel</button>';
  } else if (status === 'completed') {
    acts.innerHTML += '<span style="color:var(--green);font-size:12px;padding:4px 0;display:block;">✓ Completed</span>';
  } else if (status === 'cancelled') {
    acts.innerHTML +=
      '<button class="btn btn-ghost btn-sm" onclick="restoreItem(\'' + id + '\')">↺ Restore to scheduled</button>';
  } else if (status === 'failed') {
    acts.innerHTML += '<span style="color:var(--red);font-size:12px;padding:4px 0;display:block;">✕ Failed</span>';
  }

  acts.innerHTML +=
    '<button class="btn btn-danger btn-sm" onclick="deleteItem(\'' + id + '\')" style="margin-top:2px;">🗑 Delete</button>';

  // Position near click, keep inside viewport
  var pop = document.getElementById('cal-popover');
  pop.style.display = 'block';
  var pw = pop.offsetWidth || 280;
  var ph = pop.offsetHeight || 260;
  var x  = evt.clientX, y = evt.clientY;
  var vw = window.innerWidth, vh = window.innerHeight;
  if (x + pw + 16 > vw) x = x - pw - 8; else x = x + 10;
  if (y + ph + 16 > vh) y = Math.max(8, y - ph); else y = y + 6;
  pop.style.left = x + 'px';
  pop.style.top  = y + 'px';
}

function closePopover() {
  document.getElementById('cal-popover').style.display = 'none';
}

document.addEventListener('click', function(e) {
  var pop = document.getElementById('cal-popover');
  if (pop && pop.style.display !== 'none' && !pop.contains(e.target)) closePopover();
});
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') { closePopover(); closeReschedule(); }
});

async function _apiPost(url, body) {
  var opts = {method: 'POST'};
  if (body) {
    opts.headers = {'Content-Type': 'application/json'};
    opts.body = JSON.stringify(body);
  }
  var r = await fetch(url, opts);
  return await r.json();
}

async function cancelItem(id) {
  if (!confirm('Cancel this scheduled post?')) return;
  closePopover();
  var d = await _apiPost('/api/calendar/' + id + '/cancel');
  if (d.ok) { toast('Post cancelled', 'success'); setTimeout(function(){ location.reload(); }, 700); }
  else toast(d.error || 'Failed', 'error');
}

async function markCompleted(id) {
  closePopover();
  var d = await _apiPost('/api/calendar/' + id + '/complete');
  if (d.ok) { toast('Marked completed', 'success'); setTimeout(function(){ location.reload(); }, 700); }
  else toast(d.error || 'Failed', 'error');
}

async function restoreItem(id) {
  closePopover();
  var d = await _apiPost('/api/calendar/' + id + '/restore');
  if (d.ok) { toast('Post restored', 'success'); setTimeout(function(){ location.reload(); }, 700); }
  else toast(d.error || 'Failed', 'error');
}

async function deleteItem(id) {
  if (!confirm('Delete this calendar item?')) return;
  closePopover();
  var d = await _apiPost('/api/calendar/' + id + '/delete');
  if (d.ok) { toast('Deleted', 'success'); setTimeout(function(){ location.reload(); }, 700); }
  else toast(d.error || 'Failed', 'error');
}

function openReschedule(id, date, time) {
  closePopover();
  _currentItemId = id;
  document.getElementById('reschedule-date').value = date || '';
  document.getElementById('reschedule-time').value = time || '09:00';
  document.getElementById('reschedule-modal').style.display = 'flex';
}
function closeReschedule() {
  document.getElementById('reschedule-modal').style.display = 'none';
}
async function confirmReschedule() {
  var nd = document.getElementById('reschedule-date').value;
  var nt = document.getElementById('reschedule-time').value;
  if (!nd) { toast('Select a date', 'warn'); return; }
  closeReschedule();
  var d = await _apiPost('/api/calendar/' + _currentItemId + '/reschedule', {date: nd, time: nt});
  if (d.ok) { toast('Rescheduled', 'success'); setTimeout(function(){ location.reload(); }, 700); }
  else toast(d.error || 'Failed', 'error');
}
"""


# ── API endpoints ──────────────────────────────────────────────────
@router.post("/api/calendar/{cid}/cancel")
async def cancel_item(request: Request, cid: str):
    user = get_current_user(request)
    if not user: return JSONResponse({"error":"Unauthorized"}, status_code=401)
    update_calendar_item_status(cid, user["id"], "cancelled")
    return JSONResponse({"ok": True})


@router.post("/api/calendar/{cid}/complete")
async def complete_item(request: Request, cid: str):
    user = get_current_user(request)
    if not user: return JSONResponse({"error":"Unauthorized"}, status_code=401)
    update_calendar_item_status(cid, user["id"], "completed")
    return JSONResponse({"ok": True})


@router.post("/api/calendar/{cid}/restore")
async def restore_item(request: Request, cid: str):
    user = get_current_user(request)
    if not user: return JSONResponse({"error":"Unauthorized"}, status_code=401)
    update_calendar_item_status(cid, user["id"], "scheduled")
    return JSONResponse({"ok": True})


@router.post("/api/calendar/{cid}/delete")
async def delete_item(request: Request, cid: str):
    user = get_current_user(request)
    if not user: return JSONResponse({"error":"Unauthorized"}, status_code=401)
    delete_calendar_item(cid, user["id"])
    return JSONResponse({"ok": True})


@router.post("/api/calendar/{cid}/reschedule")
async def reschedule_item(request: Request, cid: str):
    user = get_current_user(request)
    if not user: return JSONResponse({"error":"Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error":"Invalid JSON"}, status_code=400)
    nd = body.get("date","").strip()
    nt = body.get("time","09:00").strip()
    if not nd: return JSONResponse({"error":"Date required"}, status_code=400)
    with get_conn() as conn:
        conn.execute(
            "UPDATE calendar_items SET publish_date=?, publish_time=?, status='scheduled' WHERE id=? AND user_id=?",
            (nd, nt, cid, user["id"])
        )
    return JSONResponse({"ok": True})
