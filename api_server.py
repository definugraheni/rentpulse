from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import time

from scraper_playwright import scrape_area

app = FastAPI(title="RentPulse Scrape API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache: dict[str, dict] = {}
_CACHE_TTL = 60 * 30  # 30 minutes


@app.get("/api/scrape")
def scrape(
    slug: str = Query(..., min_length=1),
    pages: int = Query(2, ge=1, le=5),
):
    slug = slug.lower().strip()

    # cek cache
    # cached = _cache.get(slug)
    # if cached and (time.time() - cached["ts"]) < _CACHE_TTL:
    #     return cached["data"]

    try:
        units, filter_info = scrape_area(slug, max_pages=pages)

    except RuntimeError as e:
        raise HTTPException(status_code=403, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"scrape failed: {e}")

    data = {
        "slug": slug,
        "label": slug.replace("-", " ").title(),
        "source_url": f"https://speedhome.com/rent/{slug}",
        "units": units,
        "filter_info": filter_info,
    }

    _cache[slug] = {
        "ts": time.time(),
        "data": data,
    }

    return data


@app.get("/")
def root():
    return {
        "status": "ok",
        "usage": "/api/scrape?slug=mont-kiara&pages=2",
    }