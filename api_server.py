from pathlib import Path
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI(title="RentPulse Scrape API")

DATA_DIR = Path("data")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/scrape")
def scrape(
    slug: str = Query(..., min_length=1),
    pages: int = Query(2, ge=1, le=5),  # dipertahankan agar frontend tidak error
):
    slug = slug.lower().strip()

    file_path = DATA_DIR / f"{slug}.json"

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Data area '{slug}' tidak ditemukan."
        )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal membaca JSON: {e}"
        )

    units = []
    filter_info = {}

    # Format JSON hasil scraper:
    # {
    #   "slug": "...",
    #   "units": [
    #       [...listings...],
    #       {...filter_info...}
    #   ]
    # }

    if isinstance(raw.get("units"), list):

        if len(raw["units"]) >= 1:
            units = raw["units"][0]

        if len(raw["units"]) >= 2:
            filter_info = raw["units"][1]

    return {
        "slug": raw.get("slug", slug),
        "label": slug.replace("-", " ").title(),
        "source_url": f"https://speedhome.com/rent/{slug}",
        "units": units,
        "filter_info": filter_info,
    }


@app.get("/")
def home():
    return FileResponse("index.html")