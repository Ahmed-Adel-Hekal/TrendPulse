# ⚡ SignalMind

<div align="center">

**AI-Powered Social Media Content Generation Platform**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-WAL_Mode-003B57?style=flat&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4?style=flat&logo=google&logoColor=white)](https://ai.google.dev)
[![License](https://img.shields.io/badge/License-MIT-D65454?style=flat)](LICENSE)

Generate scroll-stopping social media content — static posts, video scripts, and full content calendars — powered by Gemini AI, real-time trend intelligence, and competitor analysis.

[Features](#-features) • [Quick Start](#-quick-start) • [Architecture](#-architecture) • [API](#-api-reference) • [Admin](#-admin-panel) • [Configuration](#-configuration)

</div>

---

## ✦ Features

### Content Generation
- **AI Ideas** — Generate 1–10 content ideas per run with randomized tones, angles, and visual styles
- **Static Posts** — Gemini image generation (4:5 ratio, optimized for Instagram)
- **Video Scripts** — Scene-by-scene scripts with character consistency prompts for Veo 3.1
- **Multi-platform** — Instagram, TikTok, LinkedIn, Twitter/X, Facebook
- **Human-in-the-loop** — Pause after idea generation for inline editing before media is created

### Intelligence
- **Trend Engine** — 9-stage ML pipeline (KMeans clustering on sentence-transformer embeddings, velocity + novelty scoring) across 14 live data sources
- **Competitor Analysis** — Scrape competitor profiles, extract top hooks, content patterns, gap opportunities, keyword cloud
- **14 Data Sources** — Reddit, HackerNews, GitHub Trending, Google News, Google Trends, YouTube, TikTok, Instagram, LinkedIn, Dev.to, Medium, ProductHunt, StackOverflow, Twitter/X

### Planning
- **Content Calendar** — Interactive monthly calendar with click-to-manage events, reschedule modal, status tracking
- **Strategy Builder** — AI generates 7–90 day content plans and auto-seeds the calendar
- **One-click Generate** — Click any calendar event → redirected to generate form pre-filled with topic, platform, and content type

### Platform
- **Multi-language UI** — English + Arabic (MSA, Egyptian, Gulf) with full RTL layout
- **Brand Voices** — Multiple brand profiles per user (tone, audience, USP, banned words, brand color)
- **Admin Panel** — Full system administration with audit logs
- **Quota System** — Per-plan monthly generation limits (Free → Agency)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg (for video scene joining)

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows — download from https://ffmpeg.org/download.html
# Add the bin/ folder to your system PATH
```

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/signalmind.git
cd signalmind

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY and API keys (see Configuration section)

# 5. Run
python run.py
```

Open **http://localhost:8000** in your browser.

### First-time Setup

1. Register at `/register`
2. Grant yourself admin access:

```bash
python -c "
from db import init_db, get_conn
init_db()
with get_conn() as conn:
    conn.execute(\"UPDATE users SET is_admin=1 WHERE email='your@email.com'\")
print('Admin granted — visit /admin')
"
```

---

## 🏗 Architecture

```
signalmind/
├── app.py                  # FastAPI app, middleware, 10 routers
├── run.py                  # Entry point with pre-flight checks
├── db.py                   # SQLite ORM — all CRUD, quota, admin tables
├── auth.py                 # JWT, bcrypt, XSS-safe escape helpers
├── pipelines.py            # Background pipeline, scheduler, thread pools
├── ui.py                   # Server-side HTML shell, sidebar, idea cards
│
├── routes/
│   ├── auth.py             # Login, register, logout, dashboard
│   ├── generate.py         # Generate form, result page, history
│   ├── strategy.py         # Strategy generation + calendar seeding
│   ├── calendar.py         # Interactive calendar + event management API
│   ├── account.py          # Profile, API keys, language settings
│   ├── insights.py         # Trend + competitor intelligence
│   ├── brands.py           # Brand voice CRUD
│   ├── api.py              # JSON API — idea update/regen/approve
│   ├── admin.py            # Full admin panel
│   └── language.py         # Language switching
│
├── agents/
│   ├── content_agent.py    # Content generation + media pipeline
│   ├── competitor_agent.py # Competitor scraping + LLM analysis
│   └── trend_agent.py      # Trend intelligence
│
├── core/
│   ├── gemini_client.py    # Unified LLM client (Gemini + OpenRouter)
│   ├── orchestrator.py     # Pipeline coordinator
│   ├── compliance.py       # Content moderation guard
│   ├── i18n.py             # Translation system (EN + AR variants)
│   └── _styles.css         # Global CSS
│
├── media/
│   ├── static_post.py      # Gemini image generation
│   └── video_generator.py  # Veo 3.1 video generation + FFmpeg join
│
├── scraping/               # 14 source scrapers with circuit breaker
├── trend_engine/           # 9-stage ML pipeline
└── data/
    ├── saas.db             # SQLite database
    └── processed/          # Trend cache + embedding cache (24h TTL)
```

### Request Flow

```
HTTP Request
  → SecurityAndPerfMiddleware
      (reads ui_language → request.state.lang, adds security headers)
  → Rate Limiting (slowapi, optional)
  → Router Handler
      → get_current_user() — JWT cookie validation
      → Business logic
  → ui._page() — HTML response with sidebar + inline JS
```

### Generation Pipeline

```
POST /generate
  → create_generation()          # DB row, status = pending
  → BackgroundTask(_run_pipeline)
  → Redirect /result/{gid}       # Client polls every 3s

_run_pipeline
  ├── CompetitorAgent  ─── parallel
  └── TrendAgent       ───┘
       └── ContentAgent (up to 4 parallel idea threads)
            └── ComplianceGuard
                 └── MediaGeneration
                      ├── StaticPostGenerator  (Gemini Images)
                      └── VideoGenerator       (Veo 3.1 via AIML)
  → update_generation('completed') → record_usage()
```

> **Note:** `record_usage()` fires only on successful completion. Failed and cancelled generations never consume quota.

---

## 🗄 Database

SignalMind uses **SQLite in WAL mode** with a thread-local connection pool.

| Table | Purpose |
|---|---|
| `users` | Auth, plan, admin flag, ban status |
| `generations` | Jobs — config, status, result JSON, fallback flag |
| `usage` | One row per successful generation. Quota = COUNT per month |
| `brands` | Multi-brand voice profiles per user |
| `strategies` | AI-generated N-day content plans |
| `calendar_items` | Scheduled posts with publish date/time |
| `user_settings` | API keys, LLM provider, UI language preference |
| `admin_logs` | Audit trail of every admin action |
| `system_settings` | Key-value store for system-wide config |

### Quota Limits

| Plan | Generations / Month |
|---|---|
| Free | 10 |
| Starter | 50 |
| Pro | 200 |
| Agency | 1,000 |

---

## 🔌 API Reference

### Authentication

| Method | Path | Description |
|---|---|---|
| `GET` | `/login` | Login form |
| `POST` | `/login` | Submit credentials → sets `sm_token` cookie |
| `POST` | `/register` | Create account |
| `GET` | `/logout` | Delete cookie → redirect to `/login` |

### Content Generation

| Method | Path | Description |
|---|---|---|
| `GET` | `/generate` | Generation form. Accepts `?topic`, `?platform`, `?content_type`, `?from_calendar` for calendar pre-fill |
| `POST` | `/generate` | Submit → fires background pipeline → redirect `/result/{gid}` |
| `GET` | `/result/{gid}` | Result page — auto-polls while running |
| `GET` | `/history` | All user generations |
| `POST` | `/api/update-idea/{gid}/{idx}` | Save inline edits to a specific idea |
| `POST` | `/api/regenerate-idea/{gid}/{idx}` | Re-run pipeline for one idea |
| `POST` | `/api/approve-idea/{gid}/{idx}` | Trigger media generation for one idea (human-in-the-loop) |
| `GET` | `/api/idea-status/{gid}/{idx}` | Poll idea media generation status |

### Calendar

| Method | Path | Description |
|---|---|---|
| `GET` | `/calendar` | Interactive monthly calendar (`?year`, `?month`) |
| `POST` | `/api/calendar/{id}/cancel` | Cancel scheduled post |
| `POST` | `/api/calendar/{id}/complete` | Mark as completed |
| `POST` | `/api/calendar/{id}/restore` | Restore cancelled post to scheduled |
| `POST` | `/api/calendar/{id}/delete` | Hard delete |
| `POST` | `/api/calendar/{id}/reschedule` | Body: `{"date": "YYYY-MM-DD", "time": "HH:MM"}` |

---

## 🛡 Admin Panel

Access at `/admin` (requires `is_admin=1`). Every action is logged.

| Page | What you can do |
|---|---|
| **Overview** `/admin` | System stats, plan distribution chart, generation status, recent activity |
| **Users** `/admin/users` | Search/filter users, change plan, grant/revoke admin, ban with reason, impersonate (login as), hard delete |
| **Generations** `/admin/generations` | All generations across all users, cancel/delete, view config + error details |
| **Settings** `/admin/settings` | Key-value system settings, bulk clear cache, cancel all running jobs |
| **Cache** `/admin/cache` | View and clear `trend_cache.json` and `embedding_cache.pkl` |
| **Logs** `/admin/logs` | Full audit trail — who did what and when |

---

## ⚙ Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# ── CRITICAL ──────────────────────────────────────────────────────────────────
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
# Sessions will be lost on restart if this is not set.
SECRET_KEY=your_secret_key_here

# ── API Keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY=AIza...           # For text + image generation
AIML_API_KEY=...                 # For Veo 3.1 video generation
OPENROUTER_API_KEY=sk-or-...     # Optional — alternative LLM provider

# ── Server ────────────────────────────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000
DEBUG=false

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH=data/saas.db

# ── Billing (optional) ────────────────────────────────────────────────────────
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

> Users can also set their own API keys per-account at `/account`, which override the defaults.

---

## 🌍 Internationalization

| Code | Language | Direction |
|---|---|---|
| `en` | English | LTR |
| `ar` | Arabic (MSA) | RTL |
| `ar-eg` | Egyptian Arabic | RTL |
| `ar-gulf` | Gulf Arabic | RTL |

Language is stored per-user in `user_settings.ui_language`. Switch it via the flag emoji pills in the sidebar. Full RTL layout activates automatically for Arabic variants — sidebar flips, flex rows reverse, Cairo font loads, toasts appear on the left.

---

## 🎬 Media Generation

### Static Images
- Provider: **Google Gemini** (`gemini-3.1-flash-image-preview`)
- Up to 5 concurrent generations per pipeline run
- Aspect ratio: 4:5 (Instagram portrait)

### Video
- Provider: **Veo 3.1** via [AIML API](https://aimlapi.com) (`google/veo-3.1-i2v`)
- Scene-by-scene generation with character consistency via prompt anchoring
- FFmpeg joins scenes into a single `.mp4` (copy codec → libx264 fallback)
- Polling timeout: 20 minutes maximum (60 × 20s)

### Output Structure
```
outputs/
└── {user_id}/
    └── {generation_id}/
        ├── idea_1.png           # Static post image
        ├── idea1_scene1.mp4     # Individual video scenes
        ├── idea_1_full.mp4      # Joined video
        └── idea_1.json          # Video metadata
```

---

## 📈 Trend Engine

9-stage ML pipeline running across 14 data sources:

```
Raw posts → Deduplicate → Cluster (KMeans + sentence-transformers)
  → Velocity → Novelty → Time Analysis
  → Score (velocity×0.7 + novelty×0.3)
  → Classify (exploding / growing / stable)
  → Forecast → Rank (top 10 per bucket)
```

Results cached for **24 hours** in `data/processed/trend_cache.json`. Clear from `/admin/cache` to force a refresh.

---

## 🔒 Security

- **JWT** tokens stored as `HttpOnly`, `SameSite=Lax` cookies (7-day expiry)
- **bcrypt** password hashing via passlib
- **XSS prevention** — `escape_html()` and `escape_js()` applied to all user-controlled strings in templates
- **Admin guard** — `require_admin()` on every admin endpoint; returns 303 redirect (not 403) to avoid URL enumeration
- **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`
- **Atomic quota** — check-and-consume in a single DB transaction, quota charged only on successful completion
- **Rate limiting** — optional via `slowapi` (graceful fallback if not installed)

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Database | SQLite (WAL, thread-local pool) |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| LLM — Text | Google Gemini 2.5 Flash / OpenRouter |
| LLM — Images | Gemini 3.1 Flash Image Preview |
| LLM — Video | Veo 3.1 via AIML API |
| ML | scikit-learn KMeans + sentence-transformers |
| Rate Limiting | slowapi (optional) |
| Media Processing | FFmpeg + Pillow |
| Frontend | Pure server-side HTML (Python, no JS framework) |
| Fonts | DM Sans + DM Mono + Playfair Display + Cairo |

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built with ⚡ by the SignalMind team

</div>