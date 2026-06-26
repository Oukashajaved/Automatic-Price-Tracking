# Price Tracker

Track product prices across e-commerce sites and get Discord alerts when they drop.

## Quick Start

```bash
git clone <repo>
cd automated-price-tracking
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Add a Discord webhook URL in Settings → Alerts to enable price drop notifications.

## Deploy to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New + → Web Service
3. Connect your repo
4. Render auto-detects `render.yaml` — or manually set:
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `streamlit run streamlit_app.py --server.port $PORT --server.headless true`
5. Deploy

> SQLite data resets on each deploy. For persistent storage, add a Render Disk or use a hosted DB.

## Usage

- **Add a product**: Paste a URL in the sidebar
- **Check prices**: Click Check Now or set an interval in Settings
- **Alerts**: Configure Discord webhook + drop threshold in Settings
- **Test**: Use the Test tab to verify notifications

## Tests

```bash
pip install pytest
pytest
```
