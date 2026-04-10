"""routes/language.py — Language preference switching endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

from auth import get_current_user
from db import set_user_ui_language
from core.i18n import SUPPORTED_LANGUAGES, normalize_lang

router = APIRouter()


@router.get("/account/language/{lang_code}")
async def set_language(request: Request, lang_code: str):
    """
    Set the user's UI language preference.
    Called by the sidebar language switcher flag buttons.
    Redirects back to the referring page.
    """
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    # Validate
    normalized = normalize_lang(lang_code)
    if normalized not in SUPPORTED_LANGUAGES:
        normalized = "en"

    set_user_ui_language(user["id"], normalized)

    # Redirect back to wherever they came from
    referer = request.headers.get("referer", "/generate")
    # Strip host to get path only for safety
    from urllib.parse import urlparse
    parsed = urlparse(referer)
    redirect_to = parsed.path or "/generate"
    if parsed.query:
        redirect_to += "?" + parsed.query

    return RedirectResponse(redirect_to, status_code=303)


@router.post("/api/language")
async def api_set_language(request: Request):
    """JSON endpoint for AJAX language switching."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    lang = normalize_lang(body.get("language", "en"))
    if lang not in SUPPORTED_LANGUAGES:
        lang = "en"

    set_user_ui_language(user["id"], lang)
    return JSONResponse({"ok": True, "language": lang})
