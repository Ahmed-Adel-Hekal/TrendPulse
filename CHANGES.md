# TrendPulse v4 — Full Improvement Changelog

## Overview
Complete overhaul across all 7 pillars identified in the audit, plus a new Admin Panel with full system privileges.

---

## Pillar 1 — Language & UI Globalization ✅

### What was wrong
- UI always rendered in English regardless of user preference
- Arabic RTL only applied to the strategy page content div
- Sidebar, topbar, nav items, quota pill stayed LTR always
- Language selection was buried in a form dropdown on the strategy page only
- No persistence of language preference

### What was fixed
**`core/i18n.py`** — New translation system
- 7 languages: English, Arabic (MSA), Egyptian Arabic, Gulf Arabic, French, Spanish, German
- 100+ translation keys covering every UI string on every page
- `t(lang, key)` helper with automatic Arabic family fallback (ar-eg → ar → key)
- `is_rtl()`, `get_dir()`, `get_font()` helpers

**`db.py`** — `ui_language` column in `user_settings`
- Persisted per user in database
- `get_user_ui_language(uid)` for fast single-column read in middleware
- `set_user_ui_language(uid, lang)` for atomic update

**`app.py`** — Language middleware
- `SecurityAndPerfMiddleware` reads `ui_language` from user_settings on every request
- Injects into `request.state.lang` — all route handlers read from there
- No per-page cookie logic

**`ui.py`** — Global i18n + RTL
- `_sidebar_html()` accepts `lang` parameter, translates all nav items, quota label, logout button
- `_lang_switcher_html()` renders flag emoji pills in sidebar (always visible)
- `_page()` injects `dir="rtl"` on `<html>` for Arabic variants
- Loads Cairo font (Google Fonts) for Arabic scripts
- RTL CSS overrides for sidebar position, topbar, table, toasts, nav active indicator
- Admin link shown only for admin users

**`routes/language.py`** — New language switching endpoints
- `GET /account/language/{lang_code}` — sidebar flag button handler, redirects back
- `POST /api/language` — JSON API for AJAX switching

**`core/_styles.css`** — RTL-first CSS
- `[dir=rtl] .sidebar` — flipped to right, left border instead of right
- `[dir=rtl] .main` — `margin-right: var(--sidebar-w)`, `margin-left: 0`
- `[dir=rtl] .nav-item.active::before` — indicator on right side
- `[dir=rtl] .toast-wrap` — toasts appear on left for RTL users
- All flex rows reversed for RTL via `flex-direction: row-reverse`

---

## Pillar 2 — Security Hardening ✅

### What was wrong
- `/admin/stats` had no admin role check — any authenticated user could see system stats
- No rate limiting on any endpoints
- `SECRET_KEY` fell back to random value on startup — sessions invalidated on restart
- HTML templates used `.replace('"', '&quot;')` inconsistently — XSS possible

### What was fixed
**`auth.py`** — New security helpers
- `require_admin(request)` FastAPI dependency — returns 403 if not admin
- `escape_html(s)` — full 5-character HTML escape for template use
- `escape_js(s)` — safe JS string literal escape (8 substitutions including `<`, `>`, `&`)
- Startup warning log if `SECRET_KEY` not set

**`app.py`** — Security middleware
- `SecurityAndPerfMiddleware` adds `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `X-Response-Time` header for performance monitoring

**`app.py`** — Rate limiting (optional)
- `slowapi` integration — auto-enabled if package installed
- Graceful fallback if `slowapi` not installed (just logs a warning)

**`ui.py`** — XSS-safe templates
- All user-controlled strings go through `_escape_html()` before HTML insertion
- All strings in JS onclick handlers go through `_escape_js()` (not just `replace('"',...)`)
- Topic, hook, brand name, error messages — all escaped

**`run.py`** — Pre-flight check
- Warns loudly if `SECRET_KEY` not set, with instructions to generate one
- Refuses to create missing directories only if they can't be created

**`routes/admin.py`** — Admin guard on every endpoint
- `_require_admin(request)` called at the top of every handler
- Returns redirect to `/dashboard` (not 403) to avoid leaking admin URL existence

---

## Pillar 3 — Database & Connection Layer ✅

### What was wrong
- `get_conn()` opened a new SQLite connection on every call — no pooling
- `_sanitise_for_json()` ran on every DB write as a symptom fix
- `result.txt` written to cwd on every generation
- No index on `(status, scheduled_at)` — scheduler ran full table scans

### What was fixed
**`db.py`** — Thread-local connection cache
- `threading.local()` stores one connection per thread
- `@contextmanager get_conn()` yields the thread-local connection with commit/rollback
- WAL mode, `synchronous=NORMAL`, 16MB cache, mmap enabled
- `busy_timeout=5000` handles write contention gracefully

**`db.py`** — Indexes
- `CREATE INDEX IF NOT EXISTS idx_gen_status_sched ON generations(status, scheduled_at)` — scheduler query
- `idx_gen_user`, `idx_gen_status`, `idx_usage_user`, `idx_brands_user`, `idx_cal_user`, `idx_settings_user`, `idx_admin_logs`

**`db.py`** — Serialization at the right layer
- `_sanitise_for_json()` still exists as last-resort in `update_generation()`
- But now agents are expected to serialize at their boundary before passing to DB
- `media/static_post.py` and `media/video_generator.py` return proper dicts

**`agents/content_agent.py`** — Remove `result.txt`
- Debug file write removed from `content_agent.py`
- Gated behind `DEBUG=true` env var if needed

**`db.py`** — Admin tables
- `admin_logs` table for every admin action (user changes, bans, impersonation, cache clears)
- `system_settings` key-value table for admin-configurable settings

---

## Pillar 4 — Pipeline Reliability ✅

### What was wrong
- Duplicate `_run_strategy_pipeline` in both `pipelines.py` and `routes/strategy.py`
- Scheduler shared `ThreadPoolExecutor` with pipeline runners — 4 long video jobs starved the scheduler
- `record_usage()` fired at pipeline START — failed generations consumed quota
- Fallback content had no user notification

### What was fixed
**`pipelines.py`** — Removed dead duplicate
- `_run_strategy_pipeline` in `pipelines.py` deleted
- `routes/strategy.py` version is the single source of truth

**`pipelines.py`** — Separate executor pools
- `_pipeline_pool = ThreadPoolExecutor(max_workers=4)` for content generation
- `_scheduler_pool = ThreadPoolExecutor(max_workers=2)` for scheduler firing only
- Scheduler jobs never block pipeline slots

**`db.py`** — `record_usage()` moved to success path
- `update_generation()` calls `record_usage()` internally when `status == "completed"`
- Failed and cancelled generations never consume quota
- `quota_ok_atomic()` for atomic check without double-counting

**`db.py`** — Fallback flag
- `generations.fallback_used INTEGER DEFAULT 0` column
- `update_generation()` accepts `fallback_used` parameter
- Admin panel shows fallback badge on affected generations

**`ui.py`** — Fallback warning banner
- When `gen.fallback_used` is set, shows yellow alert on result page
- Translated via i18n key `gen.fallback_warn`

---

## Pillar 5 — Frontend Quality ✅

### What was wrong
- ~800 lines of HTML in Python f-strings in `ui.py`
- All JS duplicated inline as escaped strings across multiple files
- XSS in onclick attributes — user strings not properly escaped
- Toast notifications had no queue cap
- No mobile layout — sidebar covered entire viewport on small screens

### What was fixed
**`ui.py`** — JS extracted to inline block
- All JS functions moved to a single `<script>` block at bottom of `_page()`
- `saveStaticEdits`, `saveScriptChanges`, `regenerateIdea`, `approveIdea`, `approveAllIndividual`, `_pollIdeaStatus` — all in one place
- Template f-strings reference these by name without re-declaring

**`ui.py`** — XSS-safe JS attribute building
- All user strings in JS context go through `_escape_js()` which handles `'`, `"`, `\n`, `\r`, `<`, `>`, `&`
- No more `replace('"', '&quot;')` inside onclick strings

**`ui.py`** — Toast queue cap
- `while(wrap.children.length>=5) wrap.removeChild(wrap.firstChild)` — max 5 visible toasts
- Oldest dismissed first when cap reached

**`core/_styles.css`** — Mobile layout
- `@media (max-width:768px)` hides sidebar by default
- `.sidebar.open` class shows it via JS toggle
- `margin-left: 0` on `.main` for mobile
- Hamburger toggle via `topbar::before` pseudo-element

---

## Pillar 6 — Media Pipeline Robustness ✅

### What was fixed
**`media/video_generator.py`** — Polling timeout cap
- `max_polls=60` (default) parameter — 60 × 20s = 20 minute maximum
- `_poll()` returns `(None, error_message)` on timeout
- Timeout logged with clear message: `"Timed out after 60 polls (1200s)"`

**`media/video_generator.py`** — FFmpeg fallback logging
- `_run_ffmpeg()` logs warning before attempting libx264 re-encode
- Captures and logs `stderr` from failed FFmpeg runs
- Returns `False` explicitly on both failures — caller handles gracefully

**`media/static_post.py`** — Error surfacing
- `_generate_image()` returns `(path, error_message)` tuple — error always a string
- `PostResult.error` always populated on failure with actual exception message
- One retry with 2s delay before returning partial
- `generate_all()` logs per-idea failure with reason

---

## Pillar 7 — Billing & Quota Accuracy ✅

### What was fixed
**`db.py`** — Quota charged only on success
- `record_usage()` called inside `update_generation()` when `status == "completed"`
- Was previously called at pipeline start before any work was done

**`db.py`** — Atomic quota check
- `quota_ok_atomic()` reads count inside the same connection context
- Cannot be double-consumed by concurrent requests hitting the same user

**`requirements.txt`** — Stripe dependency added
- `stripe>=7.0.0` included
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*` in `.env.example`

---

## New: Admin Panel (`routes/admin.py`) ✅

Full admin panel accessible at `/admin` — admin users only.

### Pages

| URL | What it does |
|-----|-------------|
| `/admin` | Overview — 5-stat cards, plan distribution chart, generation status chart, recent activity log |
| `/admin/users` | All users with search, plan filter, status filter — edit modal with plan/admin/ban controls |
| `/admin/generations` | All generations across all users — filter by status/user, view detail, cancel, delete |
| `/admin/generations/{id}` | Single generation detail — config JSON, ideas list, error, link to user-facing result |
| `/admin/settings` | System settings key-value store — add/edit/save all settings |
| `/admin/cache` | Cache files status, size, last modified — individual and bulk clear |
| `/admin/logs` | Full admin action log — who did what and when |

### Admin Actions (all logged)

| Action | Endpoint |
|--------|---------|
| Change user plan | `POST /admin/api/user/{uid}` |
| Grant/revoke admin | `POST /admin/api/user/{uid}` |
| Ban/unban user | `POST /admin/api/user/{uid}` |
| Delete user + all data | `POST /admin/api/user/{uid}/delete` |
| Create user | `POST /admin/api/user/create` |
| Impersonate user (login as) | `POST /admin/api/impersonate/{uid}` |
| Cancel generation | `POST /admin/api/generation/{gid}/cancel` |
| Delete generation + media | `POST /admin/api/generation/{gid}/delete` |
| Cancel all running | `POST /admin/api/cancel-all-running` |
| Clear all caches | `POST /admin/api/clear-all-cache` |
| Clear specific cache | `POST /admin/api/clear-cache` |
| Set system setting | `POST /admin/api/setting/set` |

### Security
- Every endpoint calls `_require_admin(request)` — redirects to `/dashboard` if not admin
- Impersonation sets a new JWT cookie for the target user — logs the action
- User delete prevented for self-deletion
- Cache clear restricted to `data/processed/` directory — path traversal blocked

---

## Files Changed / Created

```
NEW  core/i18n.py                — Full translation system (7 languages, 100+ keys)
NEW  routes/admin.py             — Complete admin panel with all privileges
NEW  routes/language.py          — Language switching endpoints
MOD  db.py                       — Thread-local pool, atomic quota, admin tables, indexes, ui_language
MOD  auth.py                     — escape_html, escape_js, require_admin, SECRET_KEY warning
MOD  app.py                      — Security middleware, language middleware, rate limiting, admin router
MOD  ui.py                       — Full i18n, RTL, XSS-safe templates, sidebar lang switcher, toast cap
MOD  pipelines.py                — Removed duplicate, separate scheduler pool, usage on success only
MOD  media/video_generator.py    — Timeout cap (max_polls), FFmpeg error logging
MOD  media/static_post.py        — Error tuple return, proper PostResult.error surfacing
MOD  core/_styles.css            — RTL CSS, mobile layout, lang switcher styles, toast cap
NEW  run.py                      — Pre-flight checks, SECRET_KEY warning
NEW  requirements.txt            — All dependencies including slowapi, stripe
NEW  .env.example                — All environment variables documented
NEW  CHANGES.md                  — This file
```
