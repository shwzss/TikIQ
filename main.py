# main.py
import os
import time
import asyncio
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
from aiocache import cached, Cache

load_dotenv()
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKAPI_KEY = os.getenv("TIKAPI_KEY")
USE_UNOFFICIAL = os.getenv("USE_UNOFFICIAL", "false").lower() in ("1","true","yes")

templates = Jinja2Templates(directory="templates")
app = FastAPI(title="TikIQ - TikTok vidIQ (Python)")

# Basic caching for results (avoid hitting API rate limits repeatedly)
CACHE_TTL = 60  # seconds; tune for production

# Helper: call official Research API (example: query video)
async def call_tiktok_research(endpoint: str, params: dict):
    """
    Uses client credentials flow or configured method to call official TikTok Research API endpoints.
    Replace with required auth per TikTok docs. (This function is intentionally generic.)
    """
    if not (TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET):
        raise RuntimeError("TikTok developer credentials not configured.")
    # NOTE: The exact auth flow depends on which TikTok API you're using (Research, Display, etc.).
    # Here we demonstrate a client-access pattern with API key in headers.
    url = f"https://open.tiktokapis.com/{endpoint.lstrip('/')}"
    headers = {
        "x-client-key": TIKTOK_CLIENT_KEY,  # placeholder header — replace per TikTok docs
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

# Helper: fallback using tikapi (managed API) or TikTokApi (unofficial)
async def fallback_get_user(username: str, count: int = 5):
    # Prefer managed API if key available
    if TIKAPI_KEY:
        async with httpx.AsyncClient() as client:
            url = "https://api.tikapi.io/user/info"  # example endpoint; real path may differ
            headers = {"x-api-key": TIKAPI_KEY}
            resp = await client.get(url, params={"username": username}, headers=headers, timeout=20)
            resp.raise_for_status()
            return resp.json()
    if USE_UNOFFICIAL:
        # Import here to avoid import errors if not installed
        try:
            from TikTokApi import TikTokApi
        except Exception as e:
            raise RuntimeError("Unofficial TikTokApi not installed or failed to import.") from e
        with TikTokApi() as api:
            user = api.user(username=username)
            videos = []
            for v in user.videos(count=count):
                videos.append({
                    "id": v.id,
                    "create_time": v.create_time,
                    "stats": v.stats,
                    "desc": v.desc
                })
            return {"user": {"uniqueId": username}, "videos": videos}
    raise RuntimeError("No available TikTok data source configured.")

# API endpoints

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/search_user")
@cached(ttl=CACHE_TTL, cache=Cache.MEMORY)
async def api_search_user(username: str, count: int = 5):
    """
    Returns profile + recent videos for the username.
    Tries official Research API first, then fallbacks.
    """
    # Try official Research API (example path)
    try:
        if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET:
            # Example: Use research API to query videos by username
            # Real endpoints and param names may differ — check TikTok docs.
            resp = await call_tiktok_research("/v2/video/query", {"username": username, "count": count})
            return JSONResponse(content={"source": "official", "data": resp})
    except Exception as e:
        # log and continue to fallback
        print("Official API failed:", str(e))

    # fallback
    try:
        data = await fallback_get_user(username, count=count)
        return JSONResponse(content={"source": "fallback", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {e}")

@app.get("/api/video_stats")
@cached(ttl=CACHE_TTL, cache=Cache.MEMORY)
async def api_video_stats(video_id: str):
    """
    Returns metrics for a video id.
    """
    try:
        if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET:
            resp = await call_tiktok_research("/v2/video/query", {"item_id": video_id})
            return JSONResponse(content={"source": "official", "data": resp})
    except Exception as e:
        print("Official video query failed:", e)

    # fallback to tikapi or unofficial
    if TIKAPI_KEY:
        async with httpx.AsyncClient() as client:
            url = f"https://api.tikapi.io/video/{video_id}"
            headers = {"x-api-key": TIKAPI_KEY}
            r = await client.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            return JSONResponse(content={"source": "tikapi", "data": r.json()})
    if USE_UNOFFICIAL:
        try:
            from TikTokApi import TikTokApi
            with TikTokApi() as api:
                v = api.video(id=video_id)
                return JSONResponse(content={"source": "unofficial", "data": v.as_dict()})
        except Exception as e:
            print("Unofficial video fetch error:", e)

    raise HTTPException(status_code=500, detail="No data source available for video stats.")

@app.get("/api/trending_hashtags")
@cached(ttl=120, cache=Cache.MEMORY)
async def trending_hashtags(count: int = 20):
    """
    Best-effort trending hashtags list; try official display/research APIs, else fallback to managed API.
    """
    try:
        if TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET:
            resp = await call_tiktok_research("/v2/discover/hashtags", {"count": count})
            return JSONResponse(content={"source":"official","data":resp})
    except Exception as e:
        print("Official hashtags query failed:", e)

    if TIKAPI_KEY:
        async with httpx.AsyncClient() as client:
            url = "https://api.tikapi.io/trending/hashtags"
            headers = {"x-api-key": TIKAPI_KEY}
            r = await client.get(url, headers=headers, params={"count": count}, timeout=20)
            r.raise_for_status()
            return JSONResponse(content={"source":"tikapi","data":r.json()})
    # fallback: best-effort web-scrape via unofficial library (not implemented here)
    raise HTTPException(status_code=503, detail="Trending hashtags service unavailable. Configure API keys or enable fallback.")

# Simple health
@app.get("/health")
async def health():
    return {"status":"ok","time":time.time()}
