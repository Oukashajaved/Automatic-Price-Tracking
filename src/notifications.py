import requests
from src.config import get_discord_webhook


def send_price_alert(product_name, old_price, new_price, url):
    webhook = get_discord_webhook()
    if not webhook:
        return
    drop_pct = ((old_price - new_price) / old_price) * 100
    try:
        requests.post(
            webhook,
            json={
                "embeds": [
                    {
                        "title": f"Price Drop Alert!",
                        "description": f"**{product_name}**\nPrice dropped by {drop_pct:.1f}%!\n"
                        f"Old price: ${old_price:.2f}\nNew price: ${new_price:.2f}\n"
                        f"[View Product]({url})",
                        "color": 3066993,
                    }
                ]
            },
            timeout=10,
        )
    except Exception as e:
        print(f"Discord notification error: {e}")
