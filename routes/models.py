"""routes/models.py — Dynamic model catalogue endpoint.

GET /api/models?provider=google|openrouter&type=llm|image
Returns a JSON array of {id, name, description, context_length?, pricing?}
sorted by recommended-first.

The endpoint:
  1. Tries to fetch live data from the provider API (with the user's saved key).
  2. Falls back to a curated static list if the API call fails or the key is missing.
  3. Caches results in-process for 1 hour to avoid hammering provider APIs.
"""
from __future__ import annotations
import os
import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from auth import get_current_user
from db import get_user_settings

router = APIRouter()
logger = logging.getLogger("Models")

# ── In-process cache: {cache_key: (timestamp, data)} ─────────────────────────
_cache: dict[str, tuple[float, list]] = {}
_CACHE_TTL = 3600  # 1 hour


# ── Static fallback catalogues ────────────────────────────────────────────────
_STATIC: dict[str, dict[str, list]] = {
    "google": {
        "llm": [
            {"id": "gemini-2.5-flash",             "name": "Gemini 2.5 Flash",          "description": "Best speed/quality balance · recommended", "recommended": True},
            {"id": "gemini-2.5-pro",               "name": "Gemini 2.5 Pro",            "description": "Most capable Gemini model"},
            {"id": "gemini-2.0-flash",             "name": "Gemini 2.0 Flash",          "description": "Fast, efficient"},
            {"id": "gemini-2.0-flash-lite",        "name": "Gemini 2.0 Flash Lite",     "description": "Fastest · lowest cost"},
            {"id": "gemini-1.5-pro",               "name": "Gemini 1.5 Pro",            "description": "Long context (1M tokens)"},
            {"id": "gemini-1.5-flash",             "name": "Gemini 1.5 Flash",          "description": "Fast · 1M context"},
            {"id": "gemini-1.5-flash-8b",          "name": "Gemini 1.5 Flash 8B",       "description": "Smallest Gemini model"},
        ],
        "image": [
            {"id": "gemini-3.1-flash-image-preview", "name": "Gemini 3.1 Flash Image",  "description": "Latest Gemini image generation · recommended", "recommended": True},
            {"id": "gemini-2.0-flash-preview-image-generation", "name": "Gemini 2.0 Flash Image", "description": "Previous generation"},
            {"id": "imagen-3.0-generate-002",      "name": "Imagen 3.0",                "description": "High quality photorealistic images"},
            {"id": "imagen-3.0-fast-generate-001", "name": "Imagen 3.0 Fast",           "description": "Faster Imagen variant"},
        ],
    },
    "openrouter": {
        "llm": [
            {"id": "anthropic/claude-sonnet-4-5",         "name": "Claude Sonnet 4.5",        "description": "Smart, fast · recommended", "recommended": True},
            {"id": "anthropic/claude-opus-4",             "name": "Claude Opus 4",            "description": "Most capable Claude"},
            {"id": "anthropic/claude-haiku-4-5",          "name": "Claude Haiku 4.5",         "description": "Fastest Claude"},
            {"id": "openai/gpt-4o",                       "name": "GPT-4o",                   "description": "OpenAI flagship"},
            {"id": "openai/gpt-4o-mini",                  "name": "GPT-4o Mini",              "description": "Fast · affordable"},
            {"id": "openai/o3-mini",                      "name": "o3 Mini",                  "description": "OpenAI reasoning model"},
            {"id": "google/gemini-2.5-flash",             "name": "Gemini 2.5 Flash (OR)",    "description": "Via OpenRouter"},
            {"id": "google/gemini-2.5-pro",               "name": "Gemini 2.5 Pro (OR)",      "description": "Via OpenRouter"},
            {"id": "meta-llama/llama-3.3-70b-instruct",   "name": "Llama 3.3 70B",            "description": "Meta open model"},
            {"id": "mistralai/mistral-large",             "name": "Mistral Large",            "description": "Mistral flagship"},
            {"id": "deepseek/deepseek-r1",                "name": "DeepSeek R1",              "description": "Strong reasoning"},
            {"id": "deepseek/deepseek-chat-v3-0324",      "name": "DeepSeek Chat v3",         "description": "Fast DeepSeek"},
            {"id": "qwen/qwen-2.5-72b-instruct",          "name": "Qwen 2.5 72B",             "description": "Alibaba open model"},
            {"id": "x-ai/grok-3-beta",                    "name": "Grok 3 Beta",              "description": "xAI model"},
        ],
        "image": [
            {"id": "black-forest-labs/flux-1.1-pro",       "name": "Flux 1.1 Pro",            "description": "Best quality · recommended", "recommended": True},
            {"id": "black-forest-labs/flux-1.1-pro-ultra", "name": "Flux 1.1 Pro Ultra",      "description": "Highest resolution"},
            {"id": "black-forest-labs/flux-schnell",       "name": "Flux Schnell",            "description": "Fastest Flux"},
            {"id": "black-forest-labs/flux-dev",           "name": "Flux Dev",                "description": "Open weights variant"},
            {"id": "openai/dall-e-3",                      "name": "DALL·E 3",                "description": "OpenAI image generation"},
            {"id": "stability-ai/stable-diffusion-3.5",    "name": "Stable Diffusion 3.5",    "description": "Stability AI"},
            {"id": "ideogram-ai/ideogram-v2",              "name": "Ideogram v2",             "description": "Strong text-in-image"},
            {"id": "recraft-ai/recraft-v3",                "name": "Recraft v3",              "description": "Design-focused"},
        ],
    },
}


# ── Live fetchers ─────────────────────────────────────────────────────────────

def _fetch_google_models(api_key: str, model_type: str) -> list | None:
    """
    Fetch live model list from Google GenAI.
    Returns None if the call fails (caller uses static fallback).
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        all_models = list(genai.list_models())

        if model_type == "llm":
            # Models that support generateContent
            valid = [
                m for m in all_models
                if "generateContent" in (getattr(m, "supported_generation_methods", []) or [])
                and "gemini" in m.name.lower()
                and "image" not in m.name.lower()
            ]
        else:
            # Image-capable models
            valid = [
                m for m in all_models
                if any(kw in m.name.lower() for kw in ("imagen", "image"))
                or ("gemini" in m.name.lower() and "image" in m.name.lower())
            ]

        if not valid:
            return None

        results = []
        for m in valid:
            model_id = m.name.replace("models/", "")
            display  = getattr(m, "display_name", model_id)
            desc     = getattr(m, "description", "")[:120]
            # Mark our recommended model
            rec = model_id in ("gemini-2.5-flash", "gemini-3.1-flash-image-preview")
            results.append({
                "id":          model_id,
                "name":        display or model_id,
                "description": desc,
                "recommended": rec,
            })

        # Recommended first, then alphabetical
        results.sort(key=lambda x: (0 if x.get("recommended") else 1, x["id"]))
        return results

    except Exception as e:
        logger.warning("Google model fetch failed: %s", e)
        return None


def _fetch_openrouter_models(api_key: str, model_type: str) -> list | None:
    """
    Fetch live model list from OpenRouter API.
    Returns None if the call fails.
    """
    try:
        import requests
        resp = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        if resp.status_code != 200:
            return None

        data = resp.json().get("data", [])
        if not data:
            return None

        # Filter by type
        if model_type == "llm":
            # Exclude image-only models
            valid = [
                m for m in data
                if not any(kw in m.get("id", "").lower() for kw in
                           ("flux", "dall-e", "stable-diffusion", "imagen",
                            "midjourney", "ideogram", "recraft", "sdxl"))
                and m.get("context_length", 0) > 0
            ]
        else:
            # Image models
            valid = [
                m for m in data
                if any(kw in m.get("id", "").lower() for kw in
                       ("flux", "dall-e", "stable-diffusion", "imagen",
                        "ideogram", "recraft", "image"))
            ]

        if not valid:
            return None

        # Build our static recommended set for ordering
        _recommended_llm = {
            "anthropic/claude-sonnet-4-5",
            "anthropic/claude-opus-4",
            "openai/gpt-4o",
            "google/gemini-2.5-flash",
        }
        _recommended_img = {"black-forest-labs/flux-1.1-pro"}
        rec_set = _recommended_llm if model_type == "llm" else _recommended_img

        results = []
        for m in valid:
            mid   = m.get("id", "")
            name  = m.get("name", mid)
            # Build a short description from pricing
            pricing = m.get("pricing", {})
            p_prompt = pricing.get("prompt", "")
            p_compl  = pricing.get("completion", "")
            desc_parts = []
            if p_prompt:
                try:
                    cost = float(p_prompt) * 1_000_000
                    if cost == 0:
                        desc_parts.append("Free")
                    else:
                        desc_parts.append(f"${cost:.2f}/1M tokens")
                except Exception:
                    pass
            ctx = m.get("context_length")
            if ctx:
                ctx_k = ctx // 1000
                desc_parts.append(f"{ctx_k}k ctx")

            results.append({
                "id":             mid,
                "name":           name,
                "description":    " · ".join(desc_parts) if desc_parts else "",
                "recommended":    mid in rec_set,
                "context_length": ctx,
            })

        results.sort(key=lambda x: (0 if x.get("recommended") else 1, x["id"]))
        return results[:60]  # cap to avoid huge dropdowns

    except Exception as e:
        logger.warning("OpenRouter model fetch failed: %s", e)
        return None


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/api/models")
async def get_models(request: Request, provider: str = "google", type: str = "llm"):
    """
    Returns model list for the given provider and type.
    Uses live API data when possible, static fallback otherwise.

    Query params:
      provider  — "google" | "openrouter"
      type      — "llm" | "image"
    """
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    provider = provider.lower().strip()
    mtype    = type.lower().strip()

    if provider not in ("google", "openrouter"):
        return JSONResponse({"error": "Unknown provider"}, status_code=400)
    if mtype not in ("llm", "image"):
        return JSONResponse({"error": "type must be llm or image"}, status_code=400)

    # Check in-process cache
    cache_key = f"{provider}:{mtype}"
    now = time.time()
    if cache_key in _cache:
        ts, cached_data = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return JSONResponse({"models": cached_data, "source": "cache"})

    # Get user's API key
    settings = get_user_settings(user["id"])
    if provider == "google":
        api_key = settings.get("gemini_key", "") or os.getenv("GEMINI_API_KEY", "")
    else:
        api_key = settings.get("openrouter_key", "") or os.getenv("OPENROUTER_API_KEY", "")

    # Try live fetch
    live_data = None
    if api_key:
        if provider == "google":
            live_data = _fetch_google_models(api_key, mtype)
        else:
            live_data = _fetch_openrouter_models(api_key, mtype)

    if live_data:
        _cache[cache_key] = (now, live_data)
        return JSONResponse({"models": live_data, "source": "live"})

    # Fallback to static list
    static = _STATIC.get(provider, {}).get(mtype, [])
    # Don't cache fallback — retry live next request
    return JSONResponse({"models": static, "source": "static"})


@router.post("/api/models/clear-cache")
async def clear_model_cache(request: Request):
    """Admin endpoint to force-clear the model cache."""
    user = get_current_user(request)
    if not user or not user.get("is_admin"):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    _cache.clear()
    return JSONResponse({"ok": True})
