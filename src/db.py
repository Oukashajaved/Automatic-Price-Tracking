import sqlite3
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "price_history.db"


def _get_conn():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            url TEXT PRIMARY KEY, name TEXT, price REAL, currency TEXT,
            check_date TEXT, main_image_url TEXT, comparison_group TEXT
        );
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_url TEXT,
            price REAL, timestamp TEXT DEFAULT (datetime('now')),
            product_name TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );""")
    conn.commit()
    return conn


conn = _get_conn()


def get_all_products():
    return [dict(r) for r in conn.execute("SELECT * FROM products")]


def get_product(url):
    r = conn.execute("SELECT * FROM products WHERE url = ?", (url,)).fetchone()
    return dict(r) if r else None


def add_product(url, name, price, currency, main_image_url, check_date, comparison_group=None):
    conn.execute(
        "INSERT INTO products (url, name, price, currency, check_date, main_image_url, comparison_group) VALUES (?,?,?,?,?,?,?)",
        (url, name, price, currency, check_date, main_image_url, comparison_group),
    )
    conn.commit()


def update_product(url, price, name, currency, main_image_url, comparison_group=None):
    conn.execute(
        "UPDATE products SET price=?, name=?, currency=?, main_image_url=?, check_date=datetime('now'), comparison_group=? WHERE url=?",
        (price, name, currency, main_image_url, comparison_group, url),
    )
    conn.commit()


def delete_product(url):
    conn.execute("DELETE FROM price_history WHERE product_url = ?", (url,))
    conn.execute("DELETE FROM products WHERE url = ?", (url,))
    conn.commit()


def get_price_history(product_url):
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM price_history WHERE product_url = ? ORDER BY timestamp",
            (product_url,),
        )
    ]


def add_price_entry(product_url, price, product_name):
    conn.execute(
        "INSERT INTO price_history (product_url, price, product_name) VALUES (?,?,?)",
        (product_url, price, product_name),
    )
    conn.commit()


def get_setting(key, default=None):
    r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key, value):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def reset_all():
    conn.executescript("DELETE FROM price_history; DELETE FROM products; DELETE FROM settings;")
    conn.commit()
