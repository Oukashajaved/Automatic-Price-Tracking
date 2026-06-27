import requests
from src import db
from src.ai_service import AIService
from src.config import get_discord_webhook


def _send(title, description, color=3066993):
    webhook = get_discord_webhook()
    if not webhook:
        return
    try:
        requests.post(webhook, json={
            "embeds": [{"title": title, "description": description, "color": color}]
        }, timeout=10)
    except Exception as e:
        print(f"Discord error: {e}")


def send_price_alert(product_name, old_price, new_price, url):
    drop_pct = ((old_price - new_price) / old_price) * 100
    prod = db.get_product(url)
    g = prod.get("comparison_group") if prod else None
    msg = AIService().generate_ai_alert(product_name, old_price, new_price, url, g)
    _send("Price Drop!",
          f"**{product_name}** down {drop_pct:.1f}%\n${old_price:.2f} → **${new_price:.2f}**\n\n{msg}\n\n[View]({url})")


def send_outlier_alert(product_name, price, group_name, mean, std):
    dev = (price - mean) / std if std else 0
    _send("Outlier Detected",
          f"**{product_name}** is {dev:.1f}σ from group mean\nGroup: {group_name}\nPrice: ${price:.2f} (mean ${mean:.2f} ± ${std:.2f})",
          color=15158332)


def send_best_price_alert(product_name, price, url, group_name):
    _send("New Best Price",
          f"**{product_name}** is now the cheapest in **{group_name}** at ${price:.2f}\n\n[View]({url})",
          color=3066993)


def send_cross_site_alert(product_name, price, url, site, group_name):
    _send("Cross-Site Best Deal",
          f"**{product_name}** from **{site}** at ${price:.2f} is now the best deal across **{group_name}**\n\n[View]({url})",
          color=15277667)
