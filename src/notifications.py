import requests
from src import db
from src.ai_search_service import AISearchService
from src.config import get_discord_webhook


def send_price_alert(product_name, old_price, new_price, url):
    webhook = get_discord_webhook()
    if not webhook:
        return
    drop_pct = ((old_price - new_price) / old_price) * 100
    prod = db.get_product(url)
    g = prod.get("comparison_group") if prod else None
    msg = AISearchService().generate_ai_alert(product_name, old_price, new_price, url, g)
    try:
        requests.post(webhook, json={
            "embeds": [{
                "title": "Price Drop!",
                "description": f"**{product_name}** down {drop_pct:.1f}%\n${old_price:.2f} → **${new_price:.2f}**\n\n{msg}\n\n[View]({url})",
                "color": 3066993,
            }]
        }, timeout=10)
    except Exception as e:
        print(f"Discord error: {e}")
