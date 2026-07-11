# EcomScraper — Amazon & Flipkart Product Scraper

A full-stack web scraping dashboard to scrape, track, and export product data from **Amazon** and **Flipkart**.

---

## Project Structure

```
ecom scrapper/
├── backend/
│   ├── main.py               # FastAPI app — all API endpoints
│   ├── database.py           # SQLite + SQLAlchemy setup
│   ├── models.py             # Pydantic request/response schemas
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── amazon.py         # Amazon async Playwright scraper
│   │   └── flipkart.py       # Flipkart async Playwright scraper
│   └── requirements.txt
├── frontend/
│   ├── index.html            # Dashboard HTML
│   ├── style.css             # Premium dark mode CSS
│   └── app.js                # Frontend JavaScript
└── README.md
```

---

## Setup & Run

### 1. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
```

### 2. Start the backend

```bash
uvicorn main:app --reload
# Server runs at http://localhost:8000
```

### 3. Open the frontend

```bash
open ../frontend/index.html
# Or just double-click frontend/index.html in Finder
```

---

## Features

- 🔍 Scrape Amazon or Flipkart by URL or ASIN
- ⚡ Scrape both platforms simultaneously
- 📊 Dashboard with stats cards (total, Amazon count, Flipkart count, avg price)
- 📈 Price history chart (Chart.js) — tracks price changes over time
- 🧹 Filters: platform, search by name
- ↕️ Sort by: price, rating, discount, newest
- 📥 Export: CSV, JSON, Excel (.xlsx)
- 🔄 Re-scrape any saved product
- 🗑️ Delete products from history

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Server health check |
| GET | `/stats` | Dashboard statistics |
| POST | `/scrape/amazon` | Scrape Amazon product |
| POST | `/scrape/flipkart` | Scrape Flipkart product |
| POST | `/scrape/both` | Scrape both simultaneously |
| GET | `/products` | List all products |
| GET | `/products/{id}` | Get product + price history |
| DELETE | `/₹products/{id}` | Delete product |
| GET | `/export/csv` | Download CSV |
| GET | `/export/json` | Download JSON |
| GET | `/export/excel` | Download Excel |

---

## Legal Notice

> Amazon and Flipkart's Terms of Service prohibit automated scraping.
> Use this tool for personal/research purposes only.
> IP blocks and CAPTCHA challenges may occur. Selectors may change over time and require maintenance.
