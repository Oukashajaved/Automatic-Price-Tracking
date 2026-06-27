from unittest.mock import patch

import pytest

import src.db as db


@pytest.fixture(autouse=True)
def clean_db():
    conn = db._get_conn()
    for t in ["price_history", "products", "settings"]:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def test_add_and_get_product():
    db.add_product("https://example.com/p", "Test", 99.99, "USD", "https://img.com/1", "2024-01-01")
    p = db.get_product("https://example.com/p")
    assert p["name"] == "Test"
    assert p["price"] == 99.99


def test_get_all_products():
    db.add_product("https://a.com/1", "A", 10, "USD", "", "")
    db.add_product("https://a.com/2", "B", 20, "USD", "", "")
    assert len(db.get_all_products()) == 2


def test_update_product():
    db.add_product("https://example.com/p", "Old", 99.99, "USD", "", "2024-01-01")
    db.update_product("https://example.com/p", 79.99, "New", "USD", "https://img.com/2")
    p = db.get_product("https://example.com/p")
    assert p["price"] == 79.99
    assert p["name"] == "New"


def test_delete_product():
    db.add_product("https://example.com/p", "Test", 99.99, "USD", "", "")
    db.add_price_entry("https://example.com/p", 99.99, "Test")
    db.delete_product("https://example.com/p")
    assert db.get_product("https://example.com/p") is None
    assert len(db.get_price_history("https://example.com/p")) == 0


def test_price_history():
    db.add_product("https://example.com/p", "Test", 99.99, "USD", "", "")
    db.add_price_entry("https://example.com/p", 99.99, "Test")
    db.add_price_entry("https://example.com/p", 89.99, "Test")
    history = db.get_price_history("https://example.com/p")
    assert len(history) == 2
    assert history[-1]["price"] == 89.99


@patch("src.check_prices.CustomScraper")
def test_check_prices_logic(mock_scraper_cls):
    from src.check_prices import check_prices

    mock_scraper_cls.return_value.scrape_url.return_value = {
        "extract": {"name": "Test", "price": 79.99, "currency": "USD", "main_image_url": ""}
    }
    db.add_product("https://example.com/p", "Test", 99.99, "USD", "", "2024-01-01")
    db.add_price_entry("https://example.com/p", 99.99, "Test")

    updated = check_prices()
    assert updated == 1

    p = db.get_product("https://example.com/p")
    assert p["price"] == 79.99

    history = db.get_price_history("https://example.com/p")
    assert len(history) == 2


def test_settings():
    assert db.get_setting("nonexistent") is None
    assert db.get_setting("nonexistent", "default") == "default"
    db.set_setting("theme", "dark")
    assert db.get_setting("theme") == "dark"
    db.set_setting("drop_threshold", "0.1")
    assert float(db.get_setting("drop_threshold")) == 0.1
