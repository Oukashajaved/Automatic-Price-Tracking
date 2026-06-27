from src import db
from src.scraper import CustomScraper
from src.notifications import send_price_alert
from src.config import get_drop_threshold


def check_prices():
    scraper = CustomScraper()
    threshold = get_drop_threshold()
    updated = 0
    for p in db.get_all_products():
        try:
            data = scraper.scrape_url(p["url"])["extract"]
            new_price = data["price"]
            history = db.get_price_history(p["url"])
            if history and history[0]["price"] > new_price:
                if (history[0]["price"] - new_price) / history[0]["price"] >= threshold:
                    send_price_alert(p["name"], history[0]["price"], new_price, p["url"])
            db.add_price_entry(p["url"], new_price, data.get("name", p["name"]))
            db.update_product(p["url"], new_price, data.get("name", p["name"]),
                              data.get("currency", "USD"), data.get("main_image_url", ""),
                              p.get("comparison_group"))
            updated += 1
            print(f"Checked: {data.get('name', p['name'])}")
        except Exception as e:
            print(f"Error {p['url']}: {e}")
    return updated


if __name__ == "__main__":
    print(f"Checked {check_prices()} products")
