import subprocess
from pathlib import Path

# Daftar area yang akan di-scrape
AREAS = [
    "mont-kiara",
    "solaris-mont-kiara",
    "mont-kiara-bayu",
    "bukit-damansara",
    "selangor",
    "ttdi",
    "damansara-perdana",
    "kuala-lumpur",
    "sentul",
    "dutamas",
    "segambut",
    "sri-hartamas",
    "jalan-ipoh",
    "petaling-jaya",
    "cyberjaya",
    "subang-jaya",
    "puchong",
    "cheras",
    "bangsar",
    "shah-alam",
]

# Buat folder data jika belum ada
Path("data").mkdir(exist_ok=True)

for area in AREAS:
    output_file = Path("data") / f"{area}.json"

    print("=" * 60)
    print(f"Scraping: {area}")
    print("=" * 60)

    with open(output_file, "w", encoding="utf-8") as f:
        result = subprocess.run(
            ["python", "scraper_playwright.py", area],
            stdout=f,
            stderr=subprocess.PIPE,
            text=True
        )

    if result.returncode == 0:
        print(f"✅ Berhasil -> {output_file}")
    else:
        print(f"❌ Gagal -> {area}")
        print(result.stderr)

print("\n🎉 Semua proses selesai!")