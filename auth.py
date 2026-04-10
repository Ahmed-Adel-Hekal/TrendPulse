"""auth.py — Password hashing, JWT tokens, user auth helpers. (v4 — improved)"""
from __future__ import annotations
import datetime, os, secrets
from fastapi import Request
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError
from passlib.context import CryptContext
from db import get_conn, now_iso

SECRET_KEY   = os.getenv("SECRET_KEY", "")
ALGORITHM    = "HS256"
TOKEN_EXPIRE = 60 * 24 * 7  # minutes

# Warn loudly if SECRET_KEY not set — sessions die on restart
if not SECRET_KEY:
    import logging
    _log = logging.getLogger("SignalMind.auth")
    _log.critical(
        "SECRET_KEY not set in environment! Sessions will be invalidated on every restart. "
        "Set SECRET_KEY in your .env file for production use."
    )
    SECRET_KEY = secrets.token_hex(32)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)


def verify_password(p: str, h: str) -> bool:
    try:
        return pwd_ctx.verify(p, h)
    except Exception:
        return False


def create_token(uid: str) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(minutes=TOKEN_EXPIRE)
    return jwt.encode({"sub": uid, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
    except JWTError:
        return None


def get_current_user(request: Request):
    token = request.cookies.get("sm_token")
    if not token: return None
    uid = decode_token(token)
    if not uid: return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id=? AND is_active=1",
            (uid,)
        ).fetchone()
    if not row: return None
    user = dict(row)
    # Banned users cannot access the app
    if user.get("is_banned"):
        return None
    return user


def require_user(request: Request):
    """FastAPI dependency — returns user or raises 307 redirect."""
    from fastapi import HTTPException
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


def require_admin(request: Request):
    """FastAPI dependency — returns admin user or raises 403."""
    from fastapi import HTTPException
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def update_last_login(uid: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), uid))


def escape_js(s: str) -> str:
    """Safely escape a string for use inside a JS string literal."""
    if not s:
        return ""
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("<", "\\x3C")
        .replace(">", "\\x3E")
        .replace("&", "\\x26")
    )


def escape_html(s: str) -> str:
    """Basic HTML escape for user-controlled strings in templates."""
    if not s:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
