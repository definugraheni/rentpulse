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


_geocode_cache: dict = {}


def geocode_area(name: str):
    """
    Look up the real-world coordinates of the searched area name using
    OpenStreetMap's free Nominatim geocoder (no API key needed, fully
    automatic -- no manual area/coordinate list to maintain).
    Returns (lat, lng) or None if not found / request failed.
    """
    if name in _geocode_cache:
        return _geocode_cache[name]
    try:
        import urllib.request
        import urllib.parse
        query = urllib.parse.quote(f"{name}, Malaysia")
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
        req = urllib.request.Request(url, headers={
            "User-Agent": "RentPulse-PriceIntelligence/1.0 (contact: you@example.com)"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read().decode("utf-8"))
        if results:
            coords = (float(results[0]["lat"]), float(results[0]["lon"]))
            _geocode_cache[name] = coords
            time.sleep(1.0)  # respect Nominatim's 1 req/sec usage policy
            return coords
    except Exception as e:
        print(f"[geocode] failed for {name!r}: {e}", file=sys.stderr)
    _geocode_cache[name] = None
    return None


def filter_by_geo_radius(units, slug: str, max_radius_km: float = 6.0):
    """
    Keep only listings whose true coordinates (read from each card's
    embedded Google Static Map) fall within max_radius_km of the searched
    area's REAL geocoded location. Returns (filtered_units, filter_info)
    where filter_info documents exactly what was done -- so the UI can be
    fully transparent about this step rather than silently filtering.
    """
    area_name = slug.replace("-", " ").title()
    target = geocode_area(area_name)

    filter_info = {
        "method": "geo_radius",
        "area_name": area_name,
        "radius_km": max_radius_km,
        "target_lat": None,
        "target_lng": None,
        "geocode_succeeded": target is not None,
        "total_before": len(units),
        "total_after": None,
        "dropped_no_coords": 0,
        "dropped_out_of_radius": 0,
    }

    if target is None:
        # Geocoding failed -- fall back to median-of-results clustering
        # so the app still returns something, but flag it clearly.
        geo_units = [u for u in units if u.get("lat") is not None]
        if len(geo_units) >= 3:
            lats = sorted(u["lat"] for u in geo_units)
            lngs = sorted(u["lng"] for u in geo_units)
            n = len(lats)
            target = (lats[n // 2], lngs[n // 2])
            filter_info["method"] = "geo_radius_fallback_median"
        else:
            filter_info["method"] = "none_insufficient_data"
            filter_info["total_after"] = len(units)
            return units, filter_info

    target_lat, target_lng = target
    filter_info["target_lat"] = target_lat
    filter_info["target_lng"] = target_lng

    kept = []
    for u in units:
        if u.get("lat") is None:
            filter_info["dropped_no_coords"] += 1
            continue
        dist = _haversine_km(u["lat"], u["lng"], target_lat, target_lng)
        if dist <= max_radius_km:
            kept.append(u)
        else:
            filter_info["dropped_out_of_radius"] += 1

    filter_info["total_after"] = len(kept)
    return kept, filter_info

def scrape_area(slug: str, max_pages: int = 3):
    all_units = []
    seen_slugs = set()
    with sync_playwright() as p:
        # Headless Chromium inside a Docker container (Railway, Render, etc.)
        # needs these flags -- without them it can silently fail to render
        # JS-heavy pages (like SPEEDHOME's Cloudflare-protected page) even
        # though the exact same code works fine on a local Windows/Mac machine.
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
            ],
        )
        page = browser.new_page(user_agent=UA, viewport={"width": 1366, "height": 900})
        for page_num in range(1, max_pages + 1):
            html = fetch_rendered_html(page, slug, page_num)

            # Diagnostics: tell us exactly what the container actually
            # received, so we can distinguish "Cloudflare blocked us" from
            # "page loaded but parsing found nothing".
            title_m = re.search(r"<title>([^<]+)</title>", html, re.I)
            page_title = title_m.group(1) if title_m else "(no <title>)"
            print(f"[diag] page {page_num}: html_length={len(html)} title={page_title!r}", file=sys.stderr)
            if "just a moment" in html.lower() or "checking your browser" in html.lower():
                print("[diag] Cloudflare challenge page detected -- NOT the real listing page", file=sys.stderr)

            units = parse_listings(html, debug=(page_num == 1))
            print(f"[diag] page {page_num}: parsed {len(units)} unit(s) before filtering", file=sys.stderr)
            if len(units) == 0:
                detail_link_count = html.count('href="/details/') + html.count('href="https://speedhome.com/details/')
                has_title_class = "propertyTitle" in html
                has_price_class = "propertyPrice" in html
                print(f"[diag] 0 units found -- raw checks: detail_link_count={detail_link_count} "
                      f"has_propertyTitle_class={has_title_class} has_propertyPrice_class={has_price_class}", file=sys.stderr)
                print(f"[diag] html snippet (first 800 chars): {html[:800]!r}", file=sys.stderr)
            new_units = [u for u in units if u["url_slug"] not in seen_slugs]
            if not new_units:
                break
            for u in new_units:
                seen_slugs.add(u["url_slug"])
            all_units.extend(new_units)
            time.sleep(DELAY_SECONDS)
        browser.close()

    filtered, filter_info = filter_by_geo_radius(all_units, slug)
    print(f"[filter] {filter_info}", file=sys.stderr)
    return filtered, filter_info


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", help="area slug, e.g. mont-kiara, jalan-ipoh, ttdi")
    parser.add_argument("--pages", type=int, default=3, help="max pages to scrape")
    args = parser.parse_args()

    data = scrape_area(args.slug, max_pages=args.pages)
    print(json.dumps({"slug": args.slug, "units": data}, indent=2, ensure_ascii=False))