# main.py
import os
import time
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
from aiocache import cached, Cache

# Load local .env for development
load_dotenv()

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
USE_UNOFFICIAL = os.getenv("USE_UNOFFICIAL", "false").lower() in ("1", "true", "yes")

templates = Jinja2Templates(directory="templates")
app = FastAPI(title="TikIQ - TikTok vidIQ (Python)")

# Cache TTLs
SHORT_TTL = 30
MED_TTL = 120

# Helper: standardized error for missing config
def require_official_credentials():
    if not (TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET):
        raise RuntimeError("Official TikTok API credentials are not configured. Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET.")

# ========== Official TikTok API helper (generic) ==========
# NOTE: TikTok has multiple API products (Research, Display, etc.) with slightly different hostnames and auth.
# The endpoint paths used here are illustrative — replace with the exact endpoints from the TikTok Developer docs
# once you register an app and pick the API product you want.
async def call_tiktok_official(path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Generic call helper for TikTok official API endpoints.
    Replace `api_host` and exact auth header requirements according to the API product you selected.
    """
    require_official_credentials()
    params = params or {}
    # Example host; verify the correct host for the API product you use
    api_host = os.getenv("TIKTOK_API_HOST", "https://open.tiktokapis.com")
    url = api_host.rstrip("/") + path
    headers = {
        # Official auth could be OAuth Bearer or a client-key header depending on product.
        # Many endpoints require OAuth; for server-to-server Research calls, use the keys you were given.
        "x-client-key": TIKTOK_CLIENT_KEY
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

# ========== Fallback simple functions ==========
async def fallback_user_lookup(username: str, count: int = 5) -> Dict[str, Any]:
    """
    Fallback helper: returns a friendly message explaining how to enable the official API.
    (We avoid adding unreliable scrapers by default.)
    """
    return {
        "error": "no_fallback",
        "message": "No official credentials configured. To enable data, set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET. "
                   "If you want an unofficial scraper fallback, set USE_UNOFFICIAL=true and install a scraper client (not recommended).",
        "username": username
    }

# ========== API Endpoints ==========
@app.get("/", response_class=HTMLResponse)
async def ui_index(request: Request):
    # Dashboard home
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard/{username}", response_class=HTMLResponse)
async def dashboard_user(request: Request, username: str):
    # Render a dashboard page for username; the page will call our JSON endpoints for details
    return templates.TemplateResponse("dashboard.html", {"request": request, "username": username})

@app.get("/api/search_user")
@cached(ttl=MED_TTL, cache=Cache.MEMORY)
async def api_search_user(username: str = Query(..., min_length=1), count: int = 5):
    """
    Returns profile + recent videos for `username`.
    Priority:
      1) official TikTok API (if credentials configured)
      2) fallback message (no scraping enabled by default)
    """
    try:
        if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET:
            # NOTE: the path and params must match the TikTok API product you enabled.
            # Replace '/v2/user/search' with the correct endpoint.
            resp = await call_tiktok_official("/v2/user/search", {"username": username, "count": count})
            return JSONResponse(content={"source": "official", "data": resp})
    except httpx.HTTPStatusError as e:
        # pass through TikTok API error
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception:
        # try fallback
        fallback = await fallback_user_lookup(username, count)
        return JSONResponse(content={"source": "fallback", "data": fallback})

@app.get("/api/video_stats")
@cached(ttl=SHORT_TTL, cache=Cache.MEMORY)
async def api_video_stats(video_id: str = Query(..., min_length=1)):
    """
    Returns metrics for a video by id.
    """
    try:
        if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET:
            resp = await call_tiktok_official("/v2/video/query", {"item_id": video_id})
            return JSONResponse(content={"source": "official", "data": resp})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception:
        return JSONResponse(content={"source": "fallback", "data": {"error": "no_fallback", "video_id": video_id}})

@app.get("/api/trending_hashtags")
@cached(ttl=MED_TTL, cache=Cache.MEMORY)
async def api_trending_hashtags(count: int = 20):
    """
    Best-effort trending hashtags.
    """
    try:
        if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET:
            resp = await call_tiktok_official("/v2/discover/hashtags", {"count": count})
            return JSONResponse(content={"source": "official", "data": resp})
    except Exception:
        return JSONResponse(content={"source": "fallback", "data": {"error": "no_fallback"}})

@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time()}

# ========== Simple helper route to test local config ==========
@app.get("/debug/config")
async def debug_config():
    return {
        "has_tiktok_keys": bool(TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET),
        "use_unofficial": USE_UNOFFICIAL,
        "api_host_hint": os.getenv("TIKTOK_API_HOST", "https://open.tiktokapis.com")
    }
