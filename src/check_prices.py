from src import db
from src.scraper import CustomScraper
from src.notifications import send_price_alert
from src.config import get_drop_threshold


def check_prices():
    scraper = CustomScraper()
    products = db.get_all_products()
    updated = []
    threshold = get_drop_threshold()
    for p in products:
        try:
            data = scraper.scrape_url(p["url"])["extract"]
            new_price = data["price"]

            history = db.get_price_history(p["url"])
            if history:
                oldest_price = history[0]["price"]
                if oldest_price > new_price:
                    drop_pct = (oldest_price - new_price) / oldest_price
                    if drop_pct >= threshold:
                        send_price_alert(p["name"], oldest_price, new_price, p["url"])

            db.add_price_entry(p["url"], new_price, data.get("name", p["name"]))
            db.update_product(
                p["url"],
                new_price,
                data.get("name", p["name"]),
                data.get("currency", "USD"),
                data.get("main_image_url", ""),
            )
            updated.append(p["url"])
            print(f"Checked: {data.get('name', p['name'])} - ${new_price:.2f}")
        except Exception as e:
            print(f"Error checking {p['url']}: {e}")
    return updated


if __name__ == "__main__":
    print(f"Checked {len(check_prices())} products")
