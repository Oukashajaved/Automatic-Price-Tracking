# Price Tracker

Track product prices across e-commerce sites and get Discord alerts when they drop.

## Quick Start

```bash
git clone <repo>
cd automated-price-tracking
poetry install
poetry run streamlit run streamlit_app.py
```

Add a Discord webhook URL in Settings → Alerts to enable price drop notifications.

## Usage

- **Add a product**: Paste a URL in the sidebar and click Add Product
- **Check prices**: Click Check Now or set an auto-check interval in Settings
- **Alerts**: Configure a Discord webhook + drop threshold in Settings
- **Test**: Use the Test tab to verify Discord notifications work

## Tech

Python 3.10+, Streamlit, sqlite3, requests, BeautifulSoup, Plotly.

## Tests

```bash
poetry run pytest
```
