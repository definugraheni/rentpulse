"""
SPEEDHOME public-listing scraper using a real headless browser (Playwright).

Why: speedhome.com sits behind Cloudflare with a JS-based bot check. A plain
HTTP client (requests / fetch / urllib) gets a 403 because it never executes
JavaScript, so it never passes the challenge. A headless browser actually
renders the page like a real visitor, so it passes -- this is still fully
automated scraping (no manual data entry), just using a browser engine
instead of a bare HTTP client.

Setup:
    pip install playwright beautifulsoup4
    playwright install chromium

Usage:
    python scraper_playwright.py mont-kiara > mont_kiara.json
    python scraper_playwright.py jalan-ipoh --pages 2 > jalan_ipoh.json

Respects robots.txt and paces requests with a delay between pages.
"""
import sys
import json
import re
import time
import argparse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BASE = "https://speedhome.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DELAY_SECONDS = 3.0

# Hardcoded from the live robots.txt (fetched manually, since automated
# fetches of robots.txt itself get a 403 from Cloudflare using a bare
# Python User-Agent -- urllib.robotparser then silently defaults to
# "disallow everything" on that 403, which is the bug this replaces):
#
#   User-agent: *
#   Allow: /
#   Disallow: /dashboard/
#   Disallow: /_next/image
#   Disallow: /rent/*%26
#   Disallow: /sewa/*%26
#   Disallow: /zh/rent/*%26
#   Disallow: /my/sewa/*%26
_DISALLOWED_PREFIXES = ["/dashboard/", "/_next/image"]
_DISALLOWED_PATTERNS = ["/rent/*%26", "/sewa/*%26", "/zh/rent/*%26", "/my/sewa/*%26"]


def robots_allows(path: str) -> bool:
    for prefix in _DISALLOWED_PREFIXES:
        if path.startswith(prefix):
            return False
    for pattern in _DISALLOWED_PATTERNS:
        prefix, _, suffix = pattern.partition("*")
        if path.startswith(prefix) and suffix in path:
            return False
    return True  # everything else is covered by "Allow: /"


def fetch_rendered_html(page, slug: str, page_num: int) -> str:
    path = f"/rent/{slug}" + (f"?page={page_num}" if page_num > 1 else "")
    if not robots_allows(path):
        raise RuntimeError(f"robots.txt disallows {path} — aborting.")
    page.goto(f"{BASE}{path}", wait_until="domcontentloaded", timeout=45000)
    # Wait specifically for a listing card link to appear, rather than
    # waiting for ALL network activity to stop (which may never happen
    # due to background analytics/tracking requests that never end).
    try:
        page.wait_for_selector('a[href*="/details/"]', timeout=20000)
    except Exception:
        pass  # might genuinely be an area with 0 listings -- let parsing decide
    page.wait_for_timeout(1500)  # let Cloudflare's JS challenge fully settle
    return page.content()


def parse_listings(html: str, debug: bool = False):
    soup = BeautifulSoup(html, "html.parser")
    units = []
    cards = soup.select('a[href*="/details/"]')
    if debug and cards:
        with open("debug_card.html", "w", encoding="utf-8") as f:
            f.write(cards[0].prettify())
        print("Wrote debug_card.html with the first listing card's full HTML", file=sys.stderr)

    for a in cards:
        href = a.get("href", "")
        slug_m = re.search(r"/details/([a-z0-9-]+)", href)
        if not slug_m:
            continue

        # Title: <h3 class="...propertyTitle...">Real Name, Area</h3>
        h3 = a.find("h3", class_=lambda c: c and "propertyTitle" in c)
        title = h3.get_text(strip=True) if h3 else None

        # Price: <div class="...propertyPrice...">RM<!-- -->2,000<!-- --><span>/ month</span></div>
        price_div = a.find("div", class_=lambda c: c and "propertyPrice" in c)
        price_month = None
        if price_div:
            price_m = re.search(r"RM\s*([\d,]+)", price_div.get_text(" ", strip=True))
            if price_m:
                price_month = int(price_m.group(1).replace(",", ""))
        if price_month is None:
            continue  # no price = not a real listing card

        # Specs row: sqft (svg icon, no alt) + bed/bathroom/parking (img with alt="bed" etc.)
        specs = a.find("div", class_=lambda c: c and "propertySpecs" in c)
        sqft = None
        bedrooms = None
        if specs:
            for span in specs.find_all("span", recursive=False):
                img = span.find("img")
                text = span.get_text(strip=True)
                if img and img.get("alt"):
                    label = img.get("alt", "").strip().lower()
                    if label == "bed":
                        bed_val = re.sub(r"[^0-9A-Za-z]", "", text)
                        bedrooms = int(bed_val) if bed_val.isdigit() else (bed_val or None)
                else:
                    sqft_m = re.match(r"([\d,]+)", text)
                    if sqft_m:
                        sqft = int(sqft_m.group(1).replace(",", ""))

        # Extract real coordinates from the embedded Google Static Map image
        # (every card has a "Property Location Map" <img> whose src contains
        # center=LAT,LNG -- this is the property's true location, far more
        # reliable for filtering than guessing from the title text).
        lat, lng = None, None
        card_html = str(a)
        geo_m = re.search(r"center%3D(-?[\d.]+)%2C(-?[\d.]+)", card_html)
        if geo_m:
            lat, lng = float(geo_m.group(1)), float(geo_m.group(2))

        units.append({
            "title": title or text_fallback_title(a),
            "sqft": sqft,
            "bedrooms": bedrooms,
            "price_month": price_month,
            "url": f"{BASE}/details/{slug_m.group(1)}",
            "url_slug": slug_m.group(1),
            "lat": lat,
            "lng": lng,
        })
    return units


def _haversine_km(lat1, lng1, lat2, lng2):
    from math import radians, sin, cos, asin, sqrt
    R = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * R * asin(sqrt(a))


def filter_by_geo_cluster(units, max_radius_km: float = 12.0):
    """
    Automatically drop listings whose true coordinates (from the embedded
    map) are far outside the main geographic cluster of results -- handles
    SPEEDHOME pages (like /rent/jalan-ipoh) that mix in loosely-related
    areas, WITHOUT needing any manual area-name list.
    """
    geo_units = [u for u in units if u.get("lat") is not None]
    if len(geo_units) < 3:
        return units  # not enough geo data to cluster meaningfully -- keep all

    lats = sorted(u["lat"] for u in geo_units)
    lngs = sorted(u["lng"] for u in geo_units)
    n = len(lats)
    median_lat = lats[n // 2]
    median_lng = lngs[n // 2]

    kept = []
    for u in units:
        if u.get("lat") is None:
            kept.append(u)  # no coords to judge -- keep, don't punish missing data
            continue
        dist = _haversine_km(u["lat"], u["lng"], median_lat, median_lng)
        if dist <= max_radius_km:
            kept.append(u)
    return kept


def text_fallback_title(a):
    """Last-resort title if the propertyTitle <h3> isn't found for some card."""
    img = a.find("img", alt=lambda v: v and "Property Image" in v)
    if img:
        m = re.search(r"Property Image\s*\d+\s*-\s*(.+)", img["alt"])
        if m:
            return m.group(1).strip()
    return "Untitled listing"

def scrape_area(slug: str, max_pages: int = 3):
    all_units = []
    seen_slugs = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        for page_num in range(1, max_pages + 1):
            html = fetch_rendered_html(page, slug, page_num)
            units = parse_listings(html, debug=(page_num == 1))
            new_units = [u for u in units if u["url_slug"] not in seen_slugs]
            if not new_units:
                break
            for u in new_units:
                seen_slugs.add(u["url_slug"])
            all_units.extend(new_units)
            time.sleep(DELAY_SECONDS)
        browser.close()

    filtered = filter_by_geo_cluster(all_units)
    dropped = len(all_units) - len(filtered)
    if dropped:
        print(f"[filter] dropped {dropped} listing(s) geographically far from the main cluster for slug={slug!r}", file=sys.stderr)
    return filtered


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", help="area slug, e.g. mont-kiara, jalan-ipoh, ttdi")
    parser.add_argument("--pages", type=int, default=3, help="max pages to scrape")
    args = parser.parse_args()

    data = scrape_area(args.slug, max_pages=args.pages)
    print(json.dumps({"slug": args.slug, "units": data}, indent=2, ensure_ascii=False))