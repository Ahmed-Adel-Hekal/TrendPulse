"""
app.py — TrendPulse SaaS entry point (v4 — improved)

Improvements over v3:
  - Language middleware: reads ui_language from user_settings, injects into request.state
  - Security headers middleware: X-Content-Type-Options, X-Frame-Options, CSP
  - Admin route registered
  - SECRET_KEY warning on startup
  - Rate limiting via slowapi (optional)
"""
import asyncio
import logging
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from db import init_db, OUTPUT_ROOT
import pipelines  # registers pools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("TrendPulse")

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="TrendPulse SaaS", version="4.0.0")

# ── Middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


class SecurityAndPerfMiddleware(BaseHTTPMiddleware):
    """Adds security headers, perf timing, and injects ui_language into request.state."""

    async def dispatch(self, request: Request, call_next):
        import time as _t

        # Inject UI language from user session into request.state
        # so all route handlers can read request.state.lang
        try:
            from auth import decode_token
            from db import get_user_ui_language
            from core.i18n import normalize_lang

            token = request.cookies.get("sm_token", "")
            if token:
                uid = decode_token(token)
                if uid:
                    lang = get_user_ui_language(uid)
                    request.state.lang = normalize_lang(lang)
                else:
                    request.state.lang = "en"
            else:
                request.state.lang = "en"
        except Exception:
            request.state.lang = "en"

        t0       = _t.perf_counter()
        response = await call_next(request)
        ms       = round((_t.perf_counter() - t0) * 1000)

        # Performance
        response.headers["X-Response-Time"] = f"{ms}ms"
        # Security
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"]        = "SAMEORIGIN"
        response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]     = "camera=(), microphone=(), geolocation=()"

        return response


app.add_middleware(SecurityAndPerfMiddleware)

# ── Optional rate limiting (slowapi) ──────────────────────────────────────────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("Rate limiting enabled via slowapi")
except ImportError:
    logger.info("slowapi not installed — rate limiting disabled. Install with: pip install slowapi")

# ── Static files ───────────────────────────────────────────────────────────────
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_ROOT)), name="outputs")

# ── Routers ────────────────────────────────────────────────────────────────────
from routes.auth      import router as auth_router
from routes.generate  import router as generate_router
from routes.strategy  import router as strategy_router
from routes.calendar  import router as calendar_router
from routes.account   import router as account_router
from routes.insights  import router as insights_router
from routes.api       import router as api_router
from routes.admin     import router as admin_router
from routes.brands    import router as brands_router
from routes.language  import router as language_router

app.include_router(auth_router)
app.include_router(generate_router)
app.include_router(strategy_router)
app.include_router(calendar_router)
app.include_router(account_router)
app.include_router(insights_router)
app.include_router(api_router)
app.include_router(admin_router)
app.include_router(brands_router)
app.include_router(language_router)


# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(pipelines._scheduler_loop())

    # Warn loudly if SECRET_KEY is not set
    if not os.getenv("SECRET_KEY"):
        logger.critical(
            "⚠ SECRET_KEY not set in .env — sessions will die on restart! "
            "Set a random SECRET_KEY in your .env file immediately."
        )

    logger.info("TrendPulse v4 started — scheduler active")
