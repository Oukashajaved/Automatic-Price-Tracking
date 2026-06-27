# 🛒 Universal Price Tracker

Track product prices across **any e-commerce site** and get Discord alerts when they drop.

Built with Streamlit, Crawlee + Playwright for stealth scraping, and Groq AI for smart recommendations.

---

## ✨ Features

- **Universal Scraping** — Works on any e-commerce site (Amazon, eBay, Target, AliExpress, Walmart, Etsy, Shopify, WooCommerce, and more)
- **Smart Extraction** — Parses JSON-LD, Microdata, Open Graph, and generic HTML to pull product name, price, images, brand, ratings, reviews, seller info, shipping, and specs
- **Anti-Bot Bypass** — Falls back to Crawlee's Playwright crawler with stealth fingerprinting when standard requests get blocked
- **Multi-Currency** — Handles USD, EUR, GBP, PKR, INR, CAD, AUD and auto-detects currency from page content
- **Concurrent Scraping** — Searches and scrapes multiple sites in parallel using ThreadPoolExecutor
- **Price History** — Tracks price changes over time with line, bar, and scatter charts
- **Comparison Groups** — Group products across sites to compare prices side-by-side
- **AI Recommendations** — Groq-powered shopping assistant that analyzes your tracked products
- **Discord Alerts** — Get notified on price drops exceeding your threshold
- **Statistical Analysis** — Outlier detection (2σ), fraud flags, and price analytics per group

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- A Chromium browser (installed automatically)

### Installation

```bash
git clone https://github.com/your-username/universal-price-tracker.git
cd universal-price-tracker

pip install -r requirements.txt
playwright install chromium
```

### Configuration (Optional)

```bash
cp .env.example .env
```

Edit `.env` to add:
- `GROQ_API_KEY` — For AI-powered recommendations ([get one free](https://console.groq.com))
- `DISCORD_WEBHOOK_URL` — For price drop alerts
- `PRICE_DROP_THRESHOLD` — Drop percentage to trigger alerts (default: 5%)

> You can also configure these in the app's Settings tab.

### Run

```bash
streamlit run streamlit_app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 📖 Usage

### Search & Track
1. Enter a product name (e.g. "RTX 4090")
2. Select predefined sites or add custom domains
3. Click **Search & Track** — products are scraped and saved automatically

### Track a Specific URL
1. Paste any product URL in the sidebar
2. Optionally assign a comparison group
3. Click **Add URL**

### Price Monitoring
- Click **Check Now** or set an auto-check interval in Settings
- View price history charts under each comparison group
- Get Discord alerts when prices drop below your threshold

---

## 🏗️ Architecture

```
├── streamlit_app.py          # Main UI
├── src/
│   ├── scraper.py            # Universal scraper (JSON-LD → Microdata → Meta → Generic)
│   ├── site_scrapers/
│   │   ├── __init__.py       # Site registry & search_all entry point
│   │   └── search.py         # Yahoo search + concurrent scraping
│   ├── db.py                 # SQLite with thread-safe connections
│   ├── check_prices.py       # Price checker (can run standalone)
│   ├── notifications.py      # Discord webhook alerts
│   ├── ai_service.py         # Groq AI integration
│   ├── config.py             # .env loader & settings
│   └── tests/                # Unit tests
├── .streamlit/config.toml    # Streamlit theme
├── requirements.txt
└── .env.example
```

### Scraping Strategy

The scraper tries four extraction methods in order, stopping at the first one that returns a product name with a price > 0:

1. **JSON-LD** — Structured `<script type="application/ld+json">` data (most reliable)
2. **Microdata** — HTML5 `itemprop` attributes
3. **Open Graph / Meta** — `<meta>` tags (`og:title`, `product:price:amount`, etc.)
4. **Generic HTML** — CSS class heuristics + regex price patterns

If standard `requests` returns a price of 0 (JS-rendered page or bot challenge), the scraper automatically retries through Crawlee's Playwright crawler with stealth fingerprinting.

---

## 🧪 Tests

```bash
pip install pytest
python -m pytest
```

---

## 📋 Supported Sites

Works out of the box with product-path filtering for:

| Site | Domain |
|------|--------|
| Amazon | amazon.com |
| eBay | ebay.com |
| Walmart | walmart.com |
| Best Buy | bestbuy.com |
| Target | target.com |
| Newegg | newegg.com |
| AliExpress | aliexpress.com |
| Etsy | etsy.com |
| Home Depot | homedepot.com |
| Wayfair | wayfair.com |
| Costco | costco.com |

**Plus any custom domain** — just add it in the Custom Domains field. Any site using standard e-commerce markup (Shopify, WooCommerce, Magento, Squarespace) will work.

---

## 📄 License

MIT
