"""
RentPulse local API server — wraps scraper_playwright.py as an HTTP API.

Run this once, keep it running in a terminal, then open index.html
(as a static file, or via `python -m http.server` in another terminal).
index.html will call this server at http://127.0.0.1:8000/api/scrape

Setup:
    pip install fastapi uvicorn playwright beautifulsoup4
    playwright install chromium

Run:
    uvicorn api_server:app --reload --port 8000

Test:
    http://127.0.0.1:8000/api/scrape?slug=jalan-ipoh
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import time

from scraper_playwright import scrape_area  # reuses your existing scraper exactly as-is

app = FastAPI(title="RentPulse Scrape API")

# Allow index.html (opened from any local origin / file://) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# tiny in-memory cache so re-searching the same area in a session doesn't
# re-scrape immediately (still respects the scraper's own delay between pages)
_cache: dict[str, dict] = {}
_CACHE_TTL = 60 * 30  # 30 minutes


@app.get("/api/scrape")
def scrape(slug: str = Query(..., min_length=1), pages: int = Query(2, ge=1, le=5)):
    slug = slug.lower().strip()

    cached = _cache.get(slug)
    if cached and (time.time() - cached["ts"]) < _CACHE_TTL:
        return cached["data"]

    try:
        units = scrape_area(slug, max_pages=pages)
    except RuntimeError as e:
        # robots.txt disallowed this path
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"scrape failed: {e}")

    data = {
        "slug": slug,
        "label": slug.replace("-", " ").title(),
        "source_url": f"https://speedhome.com/rent/{slug}",
        "units": units,
    }
    _cache[slug] = {"ts": time.time(), "data": data}
    return data


@app.get("/")
def root():
    return {"status": "ok", "usage": "/api/scrape?slug=mont-kiara&pages=2"}
