"""ui.py — Page shell, sidebar, idea cards, HTML helpers. (v5 — premium UI)"""
from __future__ import annotations
import re
from pathlib import Path
from db import get_conn, safe_json_loads, quota_status, OUTPUT_ROOT
from core.i18n import t as _t, is_rtl, get_dir, get_font, SUPPORTED_LANGUAGES

_OUTPUT_URL_RE = re.compile(r'(outputs[/\\].+)', re.IGNORECASE)

PLAT_ICONS = {"Instagram": "📸", "TikTok": "🎬", "LinkedIn": "💼",
              "Twitter/X": "🐦", "Facebook": "👥"}


def _escape_html(s: str) -> str:
    if not s: return ""
    return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace('"',"&quot;").replace("'","&#x27;"))


def _escape_js(s: str) -> str:
    if not s: return ""
    return (str(s).replace("\\","\\\\").replace("'","\\'").replace('"','\\"')
            .replace("\n","\\n").replace("\r","\\r")
            .replace("<","\\x3C").replace(">","\\x3E").replace("&","\\x26"))


def _load_css():
    css_path = Path(__file__).parent / "core" / "_styles.css"
    if css_path.exists():
        return "<style>" + css_path.read_text(encoding="utf-8") + "</style>"
    return "<style>body{font-family:sans-serif;background:#0a0b0f;color:#e8eaf0;}</style>"


BASE_CSS = _load_css()

NAV_ITEMS = [
    ("dashboard", "⚡", "nav.dashboard",  "/dashboard"),
    ("generate",  "✦", "nav.generate",   "/generate"),
    ("strategy",  "◐", "nav.strategy",   "/strategy"),
    ("insights",  "◎", "nav.insights",   "/insights"),
    ("calendar",  "◫", "nav.calendar",   "/calendar"),
    ("history",   "◈", "nav.history",    "/history"),
    ("brands",    "◆", "nav.brands",     "/brands"),
    ("account",   "◉", "nav.account",    "/account"),
    ("pricing",   "⬡", "nav.pricing",    "/pricing"),
]


def _lang_switcher_html(current: str) -> str:
    parts = []
    for code, info in SUPPORTED_LANGUAGES.items():
        cls = "lang-sw-btn active" if code == current else "lang-sw-btn"
        parts.append(
            '<a class="' + cls + '" href="/account/language/' + code + '" title="' +
            _escape_html(info["label"]) + '">' + info["flag"] + "</a>"
        )
    return '<div class="lang-switcher">' + "".join(parts) + "</div>"


def _sidebar_html(user, active="generate", lang="en"):
    q   = quota_status(user)
    pct = round((q["used"] / max(q["limit"], 1)) * 100)

    if pct >= 90:
        bar_color = "var(--red)"
    elif pct >= 70:
        bar_color = "var(--accent)"
    else:
        bar_color = "linear-gradient(90deg, var(--accent), var(--accent2))"

    nav_html = ""
    for key, icon, label_key, href in NAV_ITEMS:
        cls = "nav-item active" if active == key else "nav-item"
        nav_html += (
            '<a class="' + cls + '" href="' + href + '">'
            '<span class="nav-icon">' + icon + "</span>"
            "<span>" + _escape_html(_t(lang, label_key)) + "</span>"
            "</a>"
        )

    admin_section = ""
    if user.get("is_admin"):
        admin_section = (
            '<div class="nav-section">' + _escape_html(_t(lang, "nav.admin_section")) + "</div>"
            '<a class="nav-item' + (" active" if active == "admin" else "") + '" href="/admin" '
            'style="color:var(--accent);">'
            '<span class="nav-icon">🛡</span>'
            "<span>" + _escape_html(_t(lang, "nav.admin")) + "</span></a>"
        )

    init  = _escape_html(user["name"][0].upper())
    name  = _escape_html(user["name"])
    plan  = _escape_html(user.get("plan", "free"))
    quota_label = _escape_html(_t(lang, "quota.label")).upper()
    used_label  = _escape_html(_t(lang, "quota.used"))
    logout_lbl  = _escape_html(_t(lang, "nav.logout"))[:3]

    rtl_attr = 'dir="rtl"' if is_rtl(lang) else ""

    return (
        '<aside class="sidebar" ' + rtl_attr + ">"
        # Shimmer top line via ::before
        '<div class="sidebar-logo">'
        '<div class="logo-icon">⚡</div>'
        '<span class="logo-text">TrendPulse</span>'
        '<span class="logo-badge">AI</span>'
        "</div>"

        '<div class="quota-pill">'
        '<div class="quota-label">' + quota_label + "</div>"
        '<div class="quota-bar-wrap">'
        '<div class="quota-bar" style="width:' + str(pct) + '%;background:' + bar_color + ';"></div>'
        "</div>"
        '<div class="quota-text">'
        "<span>" + str(q["used"]) + " / " + str(q["limit"]) + " " + used_label + "</span>"
        '<span class="plan-badge">' + plan + "</span>"
        "</div></div>"

        + _lang_switcher_html(lang) +

        '<nav class="sidebar-nav">'
        '<div class="nav-section">' + _escape_html(_t(lang, "nav.workspace")) + "</div>"
        + nav_html + admin_section +
        "</nav>"

        '<div class="sidebar-footer">'
        '<div class="user-row">'
        '<div class="user-avatar">' + init + "</div>"
        "<div class=\"user-info\">"
        '<div class="user-name">' + name + "</div>"
        '<div class="user-plan">' + plan + "</div>"
        "</div>"
        '<a class="logout-btn" href="/logout">' + logout_lbl + "</a>"
        "</div></div>"
        "</aside>"
    )


# ── Inline JS (all interactive functions) ─────────────────────────
_INLINE_JS = """
function toast(msg, type) {
  type = type || 'info';
  var icons = {success:'✓', error:'✕', info:'◈', warn:'⚠'};
  var wrap = document.getElementById('toast-wrap');
  while (wrap && wrap.children.length >= 5) wrap.removeChild(wrap.firstChild);
  var el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = '<span>' + (icons[type]||'◈') + '</span><span>' + msg + '</span>';
  if (wrap) wrap.appendChild(el);
  setTimeout(function(){ if(el.parentNode) el.remove(); }, 3800);
}
function _setStatus(gid, idx, html, active) {
  var bar = document.getElementById('idea-status-' + gid + '-' + idx);
  if (!bar) return;
  bar.innerHTML = html;
  bar.className = 'idea-status-bar' + (active ? ' active' : '');
}
function _spinner(label) {
  return '<span style="display:flex;align-items:center;gap:8px;">'
       + '<div class="spinner" style="width:14px;height:14px;border-width:2px;"></div>'
       + '<span style="font-size:12px;color:var(--text3);">' + label + '</span></span>';
}
async function saveStaticEdits(gid, idx) {
  var hook     = (document.getElementById('hook-'    + gid + '-' + idx)||{}).value||'';
  var copy     = (document.getElementById('copy-'    + gid + '-' + idx)||{}).value||'';
  var imgdesc  = (document.getElementById('imgdesc-' + gid + '-' + idx)||{}).value||'';
  _setStatus(gid, idx, _spinner('Saving…'), true);
  try {
    var r = await fetch('/api/update-idea/' + gid + '/' + idx, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({hook:hook, post_copy:copy, image_description:imgdesc})
    });
    if (!r.ok) throw new Error(await r.text());
    _setStatus(gid, idx, '<span class="regen-done">✓ Saved</span>', true);
    toast('Edits saved', 'success');
    setTimeout(function(){ _setStatus(gid, idx, '', false); }, 3000);
  } catch(e) {
    _setStatus(gid, idx, '<span class="regen-err">✕ ' + e.message + '</span>', true);
    toast('Save failed: ' + e.message, 'error');
  }
}
function _collectScript(gid, ideaIdx) {
  var scenes = [];
  document.querySelectorAll('.scene-visuals[data-gid="' + gid + '"][data-idea="' + ideaIdx + '"]').forEach(function(ta) {
    var si = parseInt(ta.dataset.scene);
    if (!scenes[si]) scenes[si] = {};
    scenes[si].visuals = ta.value;
  });
  document.querySelectorAll('.scene-voiceover[data-gid="' + gid + '"][data-idea="' + ideaIdx + '"]').forEach(function(ta) {
    var si = parseInt(ta.dataset.scene);
    if (!scenes[si]) scenes[si] = {};
    scenes[si].voiceover = ta.value;
  });
  return scenes.filter(Boolean);
}
async function saveScriptChanges(gid, idx) {
  var hook    = (document.getElementById('hook-'    + gid + '-' + idx)||{}).value||'';
  var caption = (document.getElementById('caption-' + gid + '-' + idx)||{}).value||'';
  var cta     = (document.getElementById('cta-'     + gid + '-' + idx)||{}).value||'';
  var script  = _collectScript(gid, idx);
  _setStatus(gid, idx, _spinner('Saving script…'), true);
  try {
    var r = await fetch('/api/update-idea/' + gid + '/' + idx, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({hook:hook, caption:caption, cta:{text:cta}, script:script})
    });
    if (!r.ok) throw new Error(await r.text());
    _setStatus(gid, idx, '<span class="regen-done">✓ Script saved</span>', true);
    toast('Script saved', 'success');
    setTimeout(function(){ _setStatus(gid, idx, '', false); }, 3000);
  } catch(e) {
    _setStatus(gid, idx, '<span class="regen-err">✕ ' + e.message + '</span>', true);
    toast('Save failed: ' + e.message, 'error');
  }
}
async function regenerateIdea(gid, idx) {
  var card = document.getElementById('idea-card-' + gid + '-' + idx);
  _setStatus(gid, idx, _spinner('Regenerating…'), true);
  if (card) card.style.opacity = '0.5';
  try {
    var r = await fetch('/api/regenerate-idea/' + gid + '/' + idx, {method:'POST'});
    var d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || 'Unknown error');
    _setStatus(gid, idx, '<span class="regen-done">✓ New idea ready — reloading…</span>', true);
    toast('Idea regenerated!', 'success');
    setTimeout(function(){ window.location.replace(window.location.href); }, 900);
  } catch(e) {
    if (card) card.style.opacity = '1';
    _setStatus(gid, idx, '<span class="regen-err">✕ ' + e.message + '</span>', true);
    toast('Regenerate failed: ' + e.message, 'error');
  }
}
async function approveAllIndividual(gid, n) {
  for (var i = 0; i < n; i++) {
    try {
      var r = await fetch('/api/approve-idea/' + gid + '/' + i, {method:'POST'});
      var d = await r.json();
      if (!r.ok || d.error) throw new Error(d.error||'Unknown');
      toast('Idea ' + (i+1) + ' queued ✓', 'success');
    } catch(e) { toast('Idea ' + (i+1) + ' failed: ' + e.message, 'error'); }
    await new Promise(function(res){ setTimeout(res, 700); });
  }
  toast('All ideas queued for generation', 'info');
  setTimeout(function(){ window.location.replace(window.location.href); }, 2200);
}
async function approveIdea(gid, idx) {
  _setStatus(gid, idx, _spinner('Starting media generation…'), true);
  try {
    var r = await fetch('/api/approve-idea/' + gid + '/' + idx, {method:'POST'});
    var d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error||'Unknown');
    toast('Media generation started!', 'info');
    _pollIdeaStatus(gid, idx);
  } catch(e) {
    _setStatus(gid, idx, '<span class="regen-err">✕ ' + e.message + '</span>', true);
    toast('Failed: ' + e.message, 'error');
  }
}
function _pollIdeaStatus(gid, idx) {
  var stopped = false;
  window.addEventListener('pagehide', function(){ stopped = true; }, {once:true});
  function poll() {
    if (stopped) return;
    fetch('/api/idea-status/' + gid + '/' + idx, {cache:'no-store'})
      .then(function(r){ return r.json(); })
      .then(function(d) {
        if (d.status === 'completed' || d.status === 'partial') {
          _setStatus(gid, idx, '<span class="regen-done">✓ Media ready — reloading…</span>', true);
          toast('Media ready!', 'success');
          setTimeout(function(){ window.location.replace(window.location.href); }, 1200);
        } else if (d.status === 'failed') {
          _setStatus(gid, idx, '<span class="regen-err">✕ Media generation failed</span>', true);
        } else { setTimeout(poll, 2200); }
      }).catch(function(){ if (!stopped) setTimeout(poll, 4000); });
  }
  setTimeout(poll, 2000);
}
// Mobile sidebar toggle
var _sidebarOpen = false;
function toggleSidebar() {
  _sidebarOpen = !_sidebarOpen;
  var s = document.querySelector('.sidebar');
  if (s) s.classList.toggle('open', _sidebarOpen);
}
"""


def _page(content, user, title="TrendPulse", active="generate", lang=None):
    if lang is None:
        try:
            from db import get_user_ui_language
            from core.i18n import normalize_lang
            lang = normalize_lang(get_user_ui_language(user["id"]))
        except Exception:
            lang = "en"

    rtl     = is_rtl(lang)
    dir_val = get_dir(lang)
    font    = get_font(lang)

    arabic_font = ""
    if rtl:
        arabic_font = (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">'
        )

    rtl_overrides = ""
    if rtl:
        rtl_overrides = (
            "<style>"
            "html,body{direction:rtl;}"
            ".main{margin-left:0!important;margin-right:var(--sidebar-w)!important;}"
            ".sidebar{left:auto!important;right:0!important;border-right:none!important;border-left:1px solid var(--border)!important;}"
            ".nav-item.active::before{left:auto;right:0;}"
            "[dir=rtl] .idea-card input,[dir=rtl] .idea-card textarea{unicode-bidi:plaintext;direction:auto;}"
            "</style>"
        )

    return (
        '<!DOCTYPE html><html lang="' + lang + '" dir="' + dir_val + '">'
        "<head>"
        '<meta charset="UTF-8"/>'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0"/>'
        "<title>" + _escape_html(title) + " — TrendPulse</title>"
        + arabic_font
        + BASE_CSS +
        "<style>html{font-family:" + font + ";}</style>"
        + rtl_overrides +
        "</head>"
        "<body>"
        '<div class="orb orb-1"></div><div class="orb orb-2"></div>'
        '<div class="layout">'
        + _sidebar_html(user, active, lang) +
        '<main class="main" lang="' + lang + '" dir="' + dir_val + '" style="font-family:' + font + ';">'
        # Mobile hamburger — visible on small screens
        '<div class="hamburger" onclick="toggleSidebar()" style="position:fixed;top:14px;left:14px;z-index:60;">'
        "<span></span><span></span><span></span>"
        "</div>"
        + content +
        "</main></div>"
        '<div class="toast-wrap" id="toast-wrap"></div>'
        "<script>" + _INLINE_JS + "</script>"
        "</body></html>"
    )


def _auth_page(content, title="TrendPulse"):
    return (
        "<!DOCTYPE html><html lang=\"en\">"
        "<head><meta charset=\"UTF-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\"/>"
        "<title>" + _escape_html(title) + " — TrendPulse</title>"
        + BASE_CSS +
        "</head><body>"
        '<div class="orb orb-1"></div><div class="orb orb-2"></div>'
        + content +
        '<div class="toast-wrap" id="toast-wrap"></div>'
        "<script>function toast(msg,type){type=type||'info';var el=document.createElement('div');el.className='toast '+(type||'info');el.innerHTML='<span>◈</span><span>'+msg+'</span>';var w=document.getElementById('toast-wrap');if(w){if(w.children.length>=5)w.removeChild(w.firstChild);w.appendChild(el);}setTimeout(function(){el.remove();},3500);}</script>"
        "</body></html>"
    )


def _media_display_html(uid, gid, idea_idx, ct, media):
    if not media: return ""
    status = media.get("status", "")
    if status not in ("completed", "partial"): return ""

    img_path   = media.get("image_path", "") or ""
    video_path = (
        media.get("video_path", "") or
        media.get("video_url",  "") or
        media.get("output_path","") or ""
    )
    if ct == "video" and uid and gid:
        _full = OUTPUT_ROOT / uid / gid / ("idea_" + str(idea_idx + 1) + "_full.mp4")
        if _full.exists():
            video_path = str(_full)

    def _to_url(path):
        if not path: return ""
        m = _OUTPUT_URL_RE.search(path.replace("\\", "/"))
        return "/" + m.group(1).replace("\\", "/") if m else ""

    err_msg = media.get("error", "")
    html = '<div class="media-result">'

    if ct == "video" and video_path:
        url = _to_url(video_path)
        if url:
            html += (
                '<video controls style="width:100%;max-height:420px;border-radius:var(--r2);background:#000;" src="' + url + '"></video>'
                '<div style="margin-top:8px;">'
                '<a class="btn btn-ghost btn-sm" href="' + url + '" download>↓ Download MP4</a>'
                "</div>"
            )
    elif img_path:
        url = _to_url(img_path)
        if url:
            html += (
                '<img src="' + url + '" alt="Generated image" style="width:100%;border-radius:var(--r2);max-height:520px;object-fit:cover;"/>'
                '<div style="margin-top:8px;">'
                '<a class="btn btn-ghost btn-sm" href="' + url + '" download>↓ Download image</a>'
                "</div>"
            )

    if status == "partial":
        detail = " — " + _escape_html(err_msg) if err_msg else ""
        html += '<div class="alert alert-warn mt-2" style="font-size:11px;">⚠ Media partially generated' + detail + "</div>"

    html += "</div>"
    return html


def _build_ideas_html(gen):
    result = gen.get("result") or {}
    if not result: return ""
    ideas  = result.get("ideas", [])
    ct     = gen["content_type"]
    gid    = gen["id"]
    uid    = gen.get("user_id", "")

    media_by_idx = {}
    for r in result.get("results", []):
        if isinstance(r, dict) and r.get("idea_index") is not None:
            media_by_idx[int(r["idea_index"])] = r

    compliance = result.get("compliance_report") or {}
    comp_status = compliance.get("status", "passed")
    comp_class  = {"passed":"badge-green","sanitized":"badge-amber","adjusted":"badge-red"}.get(comp_status, "badge-gray")

    fallback_warn = ""
    if gen.get("fallback_used") or result.get("fallback_used"):
        fallback_warn = (
            '<div class="alert alert-warn mb-3" style="font-size:12px;">'
            '⚠ AI returned limited content — showing fallback ideas. Try regenerating individual ideas for better results.'
            "</div>"
        )

    header = (
        fallback_warn +
        '<div class="flex gap-3 items-center mb-4" style="flex-wrap:wrap;">'
        '<span class="badge ' + comp_class + '">🛡 Compliance: ' + _escape_html(comp_status) + "</span>"
        '<span class="badge badge-gray" style="font-size:9px;">' + str(len(ideas)) + " idea(s)</span>"
        "</div>"
        '<div class="alert alert-info mb-4" style="font-size:12px;">'
        "✦ Edit any field inline, then Save — or regenerate / approve individual ideas to generate media."
        "</div>"
    )

    cards = []
    for i, idea in enumerate(ideas):
        gid_js = _escape_js(gid)
        delay  = str(i * 0.08) + "s"

        if ct == "video":
            hook     = idea.get("hook", {})
            hook_txt = hook.get("text", "") if isinstance(hook, dict) else str(hook)
            caption  = idea.get("caption", "")
            hashtags = idea.get("hashtags", [])
            script   = idea.get("script", [])
            cta      = idea.get("cta", {})
            cta_txt  = cta.get("text", "") if isinstance(cta, dict) else str(cta)

            tags = "".join(
                '<span style="background:var(--purple-dim);color:var(--purple);border:1px solid rgba(167,139,250,0.2);padding:2px 9px;border-radius:20px;font-family:var(--mono);font-size:10px;">'
                + _escape_html(h) + "</span>"
                for h in hashtags[:6]
            )

            scenes_ed = ""
            for si, s in enumerate(script):
                scenes_ed += (
                    '<div class="scene-editor">'
                    '<div class="scene-editor-header">'
                    '<span class="scene-num">Scene ' + str(s.get("scene", si+1)) + "</span>"
                    '<span class="scene-dur">' + str(s.get("duration_seconds", 8)) + "s</span>"
                    "</div>"
                    '<div class="scene-fields">'
                    "<div>"
                    '<label class="scene-field-label">Visuals</label>'
                    '<textarea class="form-textarea scene-visuals" data-gid="' + gid + '" data-idea="' + str(i) + '" data-scene="' + str(si) + '" style="min-height:60px;font-size:12px;">'
                    + _escape_html(s.get("visuals", "")) + "</textarea>"
                    "</div><div>"
                    '<label class="scene-field-label">Voiceover</label>'
                    '<textarea class="form-textarea scene-voiceover" data-gid="' + gid + '" data-idea="' + str(i) + '" data-scene="' + str(si) + '" style="min-height:50px;font-size:12px;">'
                    + _escape_html(s.get("voiceover", "")) + "</textarea>"
                    "</div></div></div>"
                )

            cards.append(
                '<div class="idea-card" id="idea-card-' + gid + "-" + str(i) + '" style="animation-delay:' + delay + ';">'
                '<div class="idea-card-header">'
                '<div class="flex items-center gap-2">'
                '<span style="font-family:var(--mono);font-size:10px;color:var(--accent);font-weight:600;">IDEA ' + str(i+1) + "</span>"
                '<span class="badge badge-purple" style="font-size:9px;">🎬 VIDEO</span>'
                "</div>"
                '<div class="idea-actions">'
                '<button class="btn btn-ghost btn-sm" onclick="saveScriptChanges(\'' + gid_js + "'," + str(i) + ')">💾 Save</button>'
                '<button class="btn btn-ghost btn-sm" onclick="regenerateIdea(\'' + gid_js + "'," + str(i) + ')">⟳ Regen</button>'
                '<button class="btn btn-green btn-sm" onclick="approveIdea(\'' + gid_js + "'," + str(i) + ')">▶ Generate video</button>'
                "</div></div>"
                '<div class="idea-body">'
                '<div class="idea-field-row">'
                '<label class="scene-field-label">Hook</label>'
                '<input class="form-input" type="text" id="hook-' + gid + "-" + str(i) + '" value="' + _escape_html(hook_txt) + '" style="font-size:14px;font-weight:600;"/>'
                "</div>"
                '<div class="idea-field-row">'
                '<label class="scene-field-label">Caption</label>'
                '<textarea class="form-textarea" id="caption-' + gid + "-" + str(i) + '" style="min-height:60px;font-size:13px;">'
                + _escape_html(caption) + "</textarea>"
                "</div>"
                '<div class="idea-field-row">'
                '<label class="scene-field-label">CTA</label>'
                '<input class="form-input" type="text" id="cta-' + gid + "-" + str(i) + '" value="' + _escape_html(cta_txt) + '" style="font-size:12px;"/>'
                "</div>"
                '<div class="scene-editor-wrap">'
                '<div class="scene-editor-title">📽 Script — ' + str(len(script)) + " scene(s)</div>"
                + scenes_ed +
                "</div>"
                '<div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:10px;">' + tags + "</div>"
                + _media_display_html(uid, gid, i, ct, media_by_idx.get(i)) +
                "</div>"
                '<div class="idea-status-bar" id="idea-status-' + gid + "-" + str(i) + '"></div>'
                "</div>"
            )
        else:
            hook     = idea.get("hook", "")
            copy_    = idea.get("post_copy", "")
            img_desc = idea.get("image_description", "")
            tags     = "".join(
                '<span style="background:var(--purple-dim);color:var(--purple);border:1px solid rgba(167,139,250,0.2);padding:2px 9px;border-radius:20px;font-family:var(--mono);font-size:10px;">'
                + _escape_html(h) + "</span>"
                for h in idea.get("hashtags", [])[:6]
            )
            cards.append(
                '<div class="idea-card" id="idea-card-' + gid + "-" + str(i) + '" style="animation-delay:' + delay + ';">'
                '<div class="idea-card-header">'
                '<div class="flex items-center gap-2">'
                '<span style="font-family:var(--mono);font-size:10px;color:var(--accent);font-weight:600;">IDEA ' + str(i+1) + "</span>"
                '<span class="badge badge-blue" style="font-size:9px;">📸 STATIC</span>'
                "</div>"
                '<div class="idea-actions">'
                '<button class="btn btn-ghost btn-sm" onclick="saveStaticEdits(\'' + gid_js + "'," + str(i) + ')">💾 Save</button>'
                '<button class="btn btn-ghost btn-sm" onclick="regenerateIdea(\'' + gid_js + "'," + str(i) + ')">⟳ Regen</button>'
                '<button class="btn btn-green btn-sm" onclick="approveIdea(\'' + gid_js + "'," + str(i) + ')">▶ Generate image</button>'
                "</div></div>"
                '<div class="idea-body">'
                '<div class="idea-field-row">'
                '<label class="scene-field-label">Hook</label>'
                '<input class="form-input" type="text" id="hook-' + gid + "-" + str(i) + '" value="' + _escape_html(hook) + '" style="font-size:14px;font-weight:600;"/>'
                "</div>"
                '<div class="idea-field-row">'
                '<label class="scene-field-label">Post copy</label>'
                '<textarea class="form-textarea" id="copy-' + gid + "-" + str(i) + '" style="min-height:80px;font-size:13px;">'
                + _escape_html(copy_) + "</textarea>"
                "</div>"
                '<div class="idea-field-row">'
                '<label class="scene-field-label">Image description</label>'
                '<textarea class="form-textarea" id="imgdesc-' + gid + "-" + str(i) + '" style="min-height:60px;font-size:12px;color:var(--text2);">'
                + _escape_html(img_desc) + "</textarea>"
                "</div>"
                '<div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:4px;">' + tags + "</div>"
                + _media_display_html(uid, gid, i, ct, media_by_idx.get(i)) +
                "</div>"
                '<div class="idea-status-bar" id="idea-status-' + gid + "-" + str(i) + '"></div>'
                "</div>"
            )

    return header + '<div style="display:flex;flex-direction:column;gap:20px;">' + "".join(cards) + "</div>"


def _build_competitor_report_html(result, gid=""):
    ci = result.get("competitor_insight") or {}
    if not ci or (ci.get("error") and not ci.get("top_hooks")):
        return ""
    hooks    = ci.get("top_hooks", [])
    gaps     = ci.get("gap_opportunities", [])
    patterns = ci.get("content_patterns", [])
    kws      = ci.get("keyword_cloud", [])
    if not (hooks or gaps or patterns):
        return ""

    rows = ""
    if hooks:
        rows += (
            '<div class="comp-stat"><strong style="color:var(--accent);">Top Hooks</strong><br>'
            + "<br>".join("· " + _escape_html(h) for h in hooks[:4]) + "</div>"
        )
    if patterns:
        rows += (
            '<div class="comp-stat"><strong style="color:var(--blue);">Content Patterns</strong><br>'
            + "<br>".join("· " + _escape_html(p) for p in patterns[:3]) + "</div>"
        )
    if gaps:
        rows += (
            '<div class="comp-stat"><strong style="color:var(--green);">Gap Opportunities</strong><br>'
            + "<br>".join("· " + _escape_html(g) for g in gaps[:3]) + "</div>"
        )
    if kws:
        rows += '<div class="comp-stat"><strong>Keywords:</strong> ' + _escape_html(", ".join(kws[:10])) + "</div>"

    link = ""
    if gid:
        link = '<a class="btn btn-ghost btn-sm" href="/insights?gen_id=' + _escape_html(gid) + '&tab=competitor" style="font-size:11px;margin-top:8px;display:inline-flex;">◎ Full Analysis →</a>'

    return (
        '<div class="comp-report">'
        '<div class="comp-report-title" style="display:flex;justify-content:space-between;align-items:center;">'
        "🔍 Competitor Intelligence" + link + "</div>"
        + rows +
        "</div>"
    )


def _get_latest_insights(uid, limit=10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, user_id, topic, result_json, created_at FROM generations "
            "WHERE user_id=? AND status='completed' AND result_json IS NOT NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (uid, min(limit, 50))
        ).fetchall()
    out = []
    for r in rows:
        result = safe_json_loads(r["result_json"], {})
        if not result: continue
        comp  = result.get("competitor_insight") or {}
        trend = result.get("trend_insight")      or {}
        out.append({
            "id": r["id"], "user_id": r["user_id"], "topic": r["topic"],
            "created_at": r["created_at"], "competitor": comp, "trend": trend,
            "has_comp":  bool(comp and isinstance(comp, dict) and (comp.get("top_hooks") or comp.get("content_patterns"))),
            "has_trend": bool(trend and isinstance(trend, dict) and (trend.get("top_trends") or trend.get("keywords"))),
        })
    return out[:limit]


def _render_competitor_panel(ci):
    if not ci or not isinstance(ci, dict):
        return (
            '<div class="card"><div class="empty-state" style="padding:40px 0;">'
            '<div class="empty-icon">🔍</div>'
            '<div class="empty-text">No competitor data</div>'
            '<div class="empty-sub">Add competitor URLs when generating content.</div>'
            "</div></div>"
        )
    if ci.get("error") and not any([ci.get("top_hooks"), ci.get("content_patterns"), ci.get("gap_opportunities")]):
        return '<div class="card"><div class="alert alert-warn">⚠ ' + _escape_html(ci.get("error","")) + "</div></div>"

    def _items(items, color="var(--text2)", limit=8):
        if not items:
            return '<div style="color:var(--text3);font-size:12px;">—</div>'
        return "".join(
            '<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:13px;color:' + color + ';">'
            '<span style="color:var(--accent);margin-right:6px;">›</span>'
            + _escape_html(str(item)[:160]) + "</div>"
            for item in items[:limit]
        )

    kw_pills = "".join(
        '<span style="background:var(--blue-dim);color:var(--blue);border:1px solid rgba(79,142,247,0.2);'
        'padding:3px 10px;border-radius:20px;font-size:11px;font-family:var(--mono);">'
        + _escape_html(kw) + "</span>"
        for kw in (ci.get("keyword_cloud") or [])[:18]
    ) or '<span style="color:var(--text3);font-size:12px;">—</span>'

    bo = ci.get("brand_overview", "")
    ts = ci.get("tone_summary", "")
    as_ = ci.get("audience_signals", "")

    return (
        (('<div class="alert alert-info mb-4" style="font-size:13px;">' + _escape_html(bo) + "</div>") if bo else "") +
        '<div class="grid-2" style="gap:16px;margin-bottom:16px;">'
        '<div class="card card-sm"><div style="font-size:11px;font-weight:600;color:var(--accent);margin-bottom:8px;letter-spacing:0.5px;text-transform:uppercase;">Top Hooks</div>' + _items(ci.get("top_hooks", []), "var(--text)") + "</div>"
        '<div class="card card-sm"><div style="font-size:11px;font-weight:600;color:var(--green);margin-bottom:8px;letter-spacing:0.5px;text-transform:uppercase;">Gap Opportunities</div>' + _items(ci.get("gap_opportunities", []), "var(--green)") + "</div>"
        "</div>"
        '<div class="grid-2" style="gap:16px;margin-bottom:16px;">'
        '<div class="card card-sm"><div style="font-size:11px;font-weight:600;color:var(--purple);margin-bottom:8px;letter-spacing:0.5px;text-transform:uppercase;">Content Patterns</div>' + _items(ci.get("content_patterns", [])) + "</div>"
        '<div class="card card-sm"><div style="font-size:11px;font-weight:600;color:var(--accent);margin-bottom:8px;letter-spacing:0.5px;text-transform:uppercase;">Winning Angles</div>' + _items(ci.get("winning_angles", [])) + "</div>"
        "</div>"
        + (('<div class="card card-sm mb-4"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Competitor Tone</div><div style="font-size:13px;color:var(--text2);">' + _escape_html(ts) + "</div></div>") if ts else "")
        + (('<div class="card card-sm mb-4"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Audience Signals</div><div style="font-size:13px;color:var(--text2);">' + _escape_html(as_) + "</div></div>") if as_ else "")
        + '<div class="card card-sm"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px;">Keywords</div><div style="display:flex;gap:6px;flex-wrap:wrap;">' + kw_pills + "</div></div>"
    )


def _render_trend_panel(ti):
    if not ti or not isinstance(ti, dict):
        return (
            '<div class="card"><div class="empty-state" style="padding:40px 0;">'
            '<div class="empty-icon">📈</div>'
            '<div class="empty-text">No trend data</div>'
            "</div></div>"
        )

    top_trends = ti.get("top_trends", [])
    keywords   = ti.get("keywords", [])
    cs         = ti.get("confidence_summary") or {}

    if not top_trends:
        return '<div class="card"><div class="alert alert-warn">No trend signals. Try clearing the cache.</div></div>'

    strength_cfg = {
        "high":   ("var(--red)",    "🔥", "Exploding"),
        "medium": ("var(--accent)", "📈", "Growing"),
        "low":    ("var(--text3)", "〰",  "Stable"),
    }

    trend_cards = ""
    for t in top_trends:
        strength            = t.get("trend_strength", "low")
        color, emoji, label = strength_cfg.get(strength, strength_cfg["low"])
        conf  = t.get("confidence_score", 0)

        fcast = t.get("forecast", "")
        fcast_badge = ""
        if fcast == "viral":
            fcast_badge = '<span style="background:var(--red-dim);color:var(--red);padding:2px 8px;border-radius:20px;font-size:10px;font-family:var(--mono);">🔥 Viral</span>'
        elif fcast == "future_trend":
            fcast_badge = '<span style="background:var(--blue-dim);color:var(--blue);padding:2px 8px;border-radius:20px;font-size:10px;font-family:var(--mono);">📡 Future</span>'

        trend_cards += (
            '<div style="border:1px solid var(--border);border-radius:var(--r);padding:16px;margin-bottom:10px;border-left:3px solid ' + color + ';transition:all 0.2s;">'
            '<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:8px;">'
            '<span style="font-size:18px;flex-shrink:0;">' + emoji + "</span>"
            '<div style="flex:1;min-width:0;">'
            '<div style="font-weight:600;font-size:14px;margin-bottom:2px;">' + _escape_html(t.get("topic", "")[:120]) + "</div>"
            '<div style="font-size:12px;color:var(--text2);">' + _escape_html(t.get("marketing_angle", "")[:140]) + "</div>"
            "</div>"
            '<div style="flex-shrink:0;text-align:right;">'
            '<div style="font-family:var(--mono);font-size:20px;font-weight:700;color:' + color + ';">' + str(conf) + "%</div>"
            '<div style="font-family:var(--mono);font-size:9px;color:var(--text3);">confidence</div>'
            "</div></div>"
            '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">'
            '<span style="background:rgba(0,0,0,0.3);color:' + color + ';padding:2px 8px;border-radius:20px;font-size:10px;font-family:var(--mono);">' + label + "</span>"
            + fcast_badge +
            "</div>"
            '<div class="progress"><div class="progress-bar" style="width:' + str(conf) + '%;background:' + color + ';"></div></div>'
            "</div>"
        )

    avg  = cs.get("average_score", 0)
    high = cs.get("high_confidence_count", 0)
    kw_pills = "".join(
        '<span style="background:var(--accent3);color:var(--accent);border:1px solid rgba(245,166,35,0.2);'
        'padding:3px 10px;border-radius:20px;font-size:11px;font-family:var(--mono);">'
        + _escape_html(k) + "</span>"
        for k in keywords[:16]
    ) if keywords else ""

    return (
        '<div class="card card-sm mb-4">'
        '<div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:12px;text-transform:uppercase;letter-spacing:0.5px;">Confidence Summary</div>'
        '<div class="grid-3" style="gap:10px;">'
        '<div style="text-align:center;padding:14px;background:var(--surface2);border-radius:var(--r2);">'
        '<div style="font-size:26px;font-weight:700;color:var(--accent);">' + str(avg) + "%</div>"
        '<div style="font-family:var(--mono);font-size:9px;color:var(--text3);letter-spacing:1px;">AVG CONFIDENCE</div>'
        "</div>"
        '<div style="text-align:center;padding:14px;background:var(--surface2);border-radius:var(--r2);">'
        '<div style="font-size:26px;font-weight:700;color:var(--green);">' + str(high) + "</div>"
        '<div style="font-family:var(--mono);font-size:9px;color:var(--text3);letter-spacing:1px;">HIGH CONFIDENCE</div>'
        "</div>"
        '<div style="text-align:center;padding:14px;background:var(--surface2);border-radius:var(--r2);">'
        '<div style="font-size:26px;font-weight:700;color:var(--text2);">' + str(len(top_trends)) + "</div>"
        '<div style="font-family:var(--mono);font-size:9px;color:var(--text3);letter-spacing:1px;">TOTAL TRENDS</div>'
        "</div></div></div>"
        + (('<div class="card card-sm mb-4"><div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px;">Hot Keywords</div><div style="display:flex;gap:6px;flex-wrap:wrap;">' + kw_pills + "</div></div>") if kw_pills else "")
        + '<div style="font-size:11px;font-weight:600;color:var(--text3);margin-bottom:12px;text-transform:uppercase;letter-spacing:0.5px;">Top Trends</div>'
        + trend_cards
    )
