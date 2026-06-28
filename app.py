from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from scraper_playwright import scrape_area

app = FastAPI(title="RentPulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Menampilkan halaman utama
@app.get("/")
def home():
    return FileResponse("index.html")

# API Scraper
@app.get("/api/scrape")
def scrape(slug: str):

    units, filter_info = scrape_area(slug)

    return {
        "label": slug.replace("-", " ").title(),
        "units": units,
        "filter_info": filter_info
    }