# RentPulse

RentPulse adalah aplikasi web **Property Price Intelligence** yang mengumpulkan data harga sewa properti dari halaman publik **SPEEDHOME Malaysia**. Aplikasi ini menampilkan ringkasan statistik harga serta daftar unit properti dalam tampilan yang responsif dan mudah digunakan.

## ✨ Features

- 🔍 Search berdasarkan nama area atau apartemen
- 📊 Price Summary (Average, Median, Mode, Fair Price)
- 🏠 Daftar lengkap unit properti
- 📏 Informasi ukuran unit (sqft)
- 🛏️ Jumlah kamar tidur
- 💰 Harga sewa bulanan dan tahunan
- 🪑 Status furnitur
- 🔗 Link langsung ke halaman listing SPEEDHOME
- 📥 Download hasil dalam format CSV

## 🛠 Tech Stack

### Backend

- FastAPI
- Playwright
- BeautifulSoup4

### Frontend

- HTML
- CSS
- JavaScript

## 📂 Project Structure

```
RentPulse/
│
├── data/                  # Cache hasil scraping
├── scraper_playwright.py  # Script scraping SPEEDHOME
├── api_server.py          # FastAPI backend
├── app.py
├── index.html
├── requirements.txt
└── README.md
```

## 🚀 Running the Project

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. (Optional) Scrape data

Contoh:

```bash
python scraper_playwright.py mont-kiara > data/mont-kiara.json
```

Atau jalankan beberapa area sekaligus:

```bash
python scrape_all.py
```

### 3. Run FastAPI

```bash
uvicorn api_server:app --reload
```

Backend akan berjalan di:

```
http://127.0.0.1:8000
```

## 📌 Notes

SPEEDHOME membatasi akses scraping dari sebagian server cloud melalui Cloudflare. Oleh karena itu, aplikasi ini menggunakan **cache JSON yang dihasilkan dari proses scraping otomatis menggunakan Playwright**. Pendekatan ini memastikan data yang ditampilkan tetap berasal dari halaman publik SPEEDHOME sekaligus membuat aplikasi dapat di-deploy dan berjalan stabil pada platform cloud gratis.

## 📄 License

This project was created for technical assessment purposes.
