import sqlite3
import threading
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "price_history.db"

SCHEMA_VERSION = 3

_local = threading.local()


def _get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                url TEXT PRIMARY KEY, name TEXT, price REAL, currency TEXT DEFAULT 'USD',
                check_date TEXT, main_image_url TEXT DEFAULT '', comparison_group TEXT,
                seller TEXT DEFAULT '', seller_rating TEXT DEFAULT '',
                review_count INTEGER DEFAULT 0, condition TEXT DEFAULT '',
                shipping TEXT DEFAULT '', site TEXT DEFAULT '', last_updated TEXT,
                images TEXT DEFAULT '[]', brand TEXT DEFAULT '', rating REAL DEFAULT 0.0,
                description TEXT DEFAULT '', specs TEXT DEFAULT '{}'
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
        _migrate(conn)
        _local.conn = conn
    return _local.conn


def _migrate(conn):
    ver = conn.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
    ver = int(ver["value"]) if ver else 0
    if ver < SCHEMA_VERSION:
        conn.executescript("DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS price_history;")
        conn.executescript("""
            CREATE TABLE products (
                url TEXT PRIMARY KEY, name TEXT, price REAL, currency TEXT DEFAULT 'USD',
                check_date TEXT, main_image_url TEXT DEFAULT '', comparison_group TEXT,
                seller TEXT DEFAULT '', seller_rating TEXT DEFAULT '',
                review_count INTEGER DEFAULT 0, condition TEXT DEFAULT '',
                shipping TEXT DEFAULT '', site TEXT DEFAULT '', last_updated TEXT,
                images TEXT DEFAULT '[]', brand TEXT DEFAULT '', rating REAL DEFAULT 0.0,
                description TEXT DEFAULT '', specs TEXT DEFAULT '{}'
            );
            CREATE TABLE price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_url TEXT,
                price REAL, timestamp TEXT DEFAULT (datetime('now')),
                product_name TEXT
            );""")
        conn.executescript(f"INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '{SCHEMA_VERSION}')")
        conn.commit()


def get_all_products():
    return [dict(r) for r in _get_conn().execute("SELECT * FROM products")]


def get_product(url):
    r = _get_conn().execute("SELECT * FROM products WHERE url = ?", (url,)).fetchone()
    return dict(r) if r else None


def add_product(url, name, price, currency="USD", main_image_url="", check_date="", comparison_group=None,
                seller="", seller_rating="", review_count=0, condition="", shipping="", site="",
                images="[]", brand="", rating=0.0, description="", specs="{}"):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO products (url, name, price, currency, check_date, main_image_url, comparison_group, seller, seller_rating, review_count, condition, shipping, site, last_updated, images, brand, rating, description, specs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),?,?,?,?,?)",
        (url, name, price, currency, check_date, main_image_url, comparison_group, seller, seller_rating, review_count, condition, shipping, site, images, brand, rating, description, specs),
    )
    conn.commit()


def update_product(url, price, name, currency="USD", main_image_url="", comparison_group=None,
                   seller="", seller_rating="", review_count=0, condition="", shipping="", site="",
                   images="[]", brand="", rating=0.0, description="", specs="{}"):
    conn = _get_conn()
    conn.execute(
        "UPDATE products SET price=?, name=?, currency=?, main_image_url=?, check_date=datetime('now'), comparison_group=?, seller=?, seller_rating=?, review_count=?, condition=?, shipping=?, site=?, last_updated=datetime('now'), images=?, brand=?, rating=?, description=?, specs=? WHERE url=?",
        (price, name, currency, main_image_url, comparison_group, seller, seller_rating, review_count, condition, shipping, site, images, brand, rating, description, specs, url),
    )
    conn.commit()


def delete_product(url):
    conn = _get_conn()
    conn.execute("DELETE FROM price_history WHERE product_url = ?", (url,))
    conn.execute("DELETE FROM products WHERE url = ?", (url,))
    conn.commit()


def get_price_history(product_url):
    return [
        dict(r)
        for r in _get_conn().execute(
            "SELECT * FROM price_history WHERE product_url = ? ORDER BY timestamp",
            (product_url,),
        )
    ]


def add_price_entry(product_url, price, product_name):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO price_history (product_url, price, product_name) VALUES (?,?,?)",
        (product_url, price, product_name),
    )
    conn.commit()


def get_setting(key, default=None):
    r = _get_conn().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key, value):
    conn = _get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def reset_all():
    conn = _get_conn()
    conn.executescript("DROP TABLE IF EXISTS price_history; DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS settings;")
    conn.commit()
    conn.close()
    _local.conn = None
    _get_conn()
