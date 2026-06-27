from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scraper_playwright import scrape_area

app = FastAPI(title="RentPulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "RentPulse API Running"
    }

@app.get("/api/scrape")
def scrape(slug: str):
    units = scrape_area(slug)

    return {
        "label": slug.replace("-", " ").title(),
        "units": units
    }