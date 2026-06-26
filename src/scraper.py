import json
import random
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class CustomScraper:
    __USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def scrape_url(self, url):
        for method_name in ["_from_jsonld", "_from_microdata", "_from_meta", "_from_generic"]:
            data = getattr(self, method_name)(url)
            if data and data["name"] and data["price"] > 0:
                return {"extract": data}
        try:
            data = self._from_playwright(url)
            if data and data["name"] and data["price"] > 0:
                return {"extract": data}
        except Exception as e:
            print(f"Playwright error: {e}")
        raise Exception(f"Could not scrape: {url}")

    def _from_jsonld(self, url):
        soup = self._soup(url)
        if not soup:
            return None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = json.loads(script.string.strip())
                items = raw if isinstance(raw, list) else raw.get("@graph", [raw])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    types = item.get("@type", "")
                    if "Product" not in (types if isinstance(types, list) else [types]):
                        continue
                    name = item.get("name")
                    if not name:
                        continue
                    img = item.get("image")
                    if isinstance(img, list):
                        img = img[0]
                    if isinstance(img, dict):
                        img = img.get("url") or ""
                    if not isinstance(img, str):
                        img = ""
                    price = None
                    currency = "USD"
                    offers = item.get("offers")
                    if isinstance(offers, dict):
                        price = offers.get("price")
                        currency = offers.get("priceCurrency", "USD")
                    elif isinstance(offers, list):
                        for o in offers:
                            if isinstance(o, dict) and o.get("price"):
                                price = o.get("price")
                                currency = o.get("priceCurrency", "USD")
                                break
                    if price is not None:
                        return {
                            "name": name,
                            "price": self._extract_price(str(price)),
                            "currency": currency or "USD",
                            "main_image_url": urljoin(url, img) if img else "",
                        }
            except Exception:
                pass
        return None

    def _from_microdata(self, url):
        soup = self._soup(url)
        if not soup:
            return None
        data = {"name": "", "price": 0.0, "currency": "USD", "main_image_url": ""}

        name_el = soup.find(itemprop="name")
        if name_el:
            data["name"] = name_el.get("content") or name_el.get_text().strip()

        price_el = soup.find(itemprop="price")
        if price_el:
            data["price"] = self._extract_price(price_el.get("content") or price_el.get_text())
            curr_el = soup.find(itemprop="priceCurrency")
            if curr_el:
                data["currency"] = curr_el.get("content") or curr_el.get_text()

        img_el = soup.find(itemprop="image")
        if img_el:
            src = img_el.get("src") or img_el.get("content") or img_el.get("href")
            if src:
                data["main_image_url"] = urljoin(url, src)

        return data if data["name"] or data["price"] > 0 else None

    def _from_meta(self, url):
        soup = self._soup(url)
        if not soup:
            return None
        data = {"name": "", "price": 0.0, "currency": "USD", "main_image_url": ""}

        for prop in ["og:title", "twitter:title", "product:title"]:
            m = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if m and m.get("content"):
                data["name"] = m["content"]
                break

        for prop in ["product:price:amount", "og:price:amount"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                data["price"] = self._extract_price(m["content"])
                break
        if data["price"] == 0.0:
            m = soup.find("meta", attrs={"name": "twitter:data1"})
            if m and m.get("value"):
                data["price"] = self._extract_price(m["value"])

        for prop in ["product:price:currency", "og:price:currency"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                data["currency"] = m["content"]
                break

        for prop in ["og:image", "twitter:image"]:
            m = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if m and m.get("content"):
                data["main_image_url"] = urljoin(url, m["content"])
                break
        if not data["main_image_url"]:
            m = soup.find("link", rel="image_src")
            if m and m.get("href"):
                data["main_image_url"] = urljoin(url, m["href"])

        return data if data["name"] or data["price"] > 0 else None

    def _from_generic(self, url):
        soup = self._soup(url)
        if not soup:
            return None
        data = {"name": "", "price": 0.0, "currency": "USD", "main_image_url": ""}

        h1 = soup.find("h1")
        if h1:
            data["name"] = h1.get_text().strip()
        if not data["name"]:
            tt = soup.find("title")
            if tt:
                t = tt.get_text().strip()
                sep = re.search(r"\s[–\-—|]\s", t)
                data["name"] = t[:sep.start()].strip() if sep else t

        price_pat = re.compile(r"^\s*[$€£¥₽]?\s*[\d,]+\.\d{2}\s*$")
        for tag in soup.find_all(class_=re.compile(r"(^|[\s-])price($|[\s-])", re.I)):
            txt = tag.get_text().strip()
            if price_pat.match(txt):
                raw = txt
                data["price"] = self._extract_price(raw)
                c = self._detect_currency(txt)
                if c:
                    data["currency"] = c
                break
        if data["price"] == 0.0:
            for tag in soup.find_all(string=re.compile(r"^\$[\d,]+\.\d{2}$")):
                data["price"] = self._extract_price(tag.strip())
                if data["price"] > 0:
                    break

        for tag in soup.find_all("img", class_=re.compile(r"(^|[\s-])product($|[\s-])", re.I)):
            src = tag.get("src") or tag.get("data-src")
            if src and not src.startswith("data:"):
                data["main_image_url"] = urljoin(url, src)
                break
        if not data["main_image_url"]:
            for tag in soup.find_all("img", limit=5):
                src = tag.get("src") or tag.get("data-src")
                if src and "logo" not in src.lower() and not src.startswith("data:"):
                    data["main_image_url"] = urljoin(url, src)
                    break

        return data if data["name"] else None

    def _from_playwright(self, url):
        from playwright.sync_api import sync_playwright

        soup = None
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=random.choice(self.__USER_AGENTS),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=25000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            soup = BeautifulSoup(page.content(), "html.parser")
            browser.close()

        if not soup:
            return None

        for method in [self._parse_jsonld_from_soup, self._parse_meta_from_soup, self._parse_generic_from_soup]:
            data = method(soup, url)
            if data and data["name"] and data["price"] > 0:
                return data
        return None

    def _soup(self, url):
        html = self._fetch(url)
        return BeautifulSoup(html, "html.parser") if html else None

    def _fetch(self, url):
        ua = random.choice(self.__USER_AGENTS)
        self._session.headers.update({
            "User-Agent": ua,
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        parsed = urlparse(url)
        try:
            self._session.get(f"{parsed.scheme}://{parsed.netloc}", headers={"User-Agent": ua}, timeout=10)
            resp = self._session.get(url, timeout=20)
            if resp.status_code in (403, 503):
                import time
                time.sleep(2)
                resp = requests.get(
                    url,
                    headers={
                        "User-Agent": ua,
                        "Accept": "text/html,*/*",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": f"https://www.google.com/",
                    },
                    timeout=20,
                )
            return resp.text if resp.status_code == 200 else ""
        except Exception as e:
            print(f"HTTP error: {e}")
            return ""

    @staticmethod
    def _extract_price(s):
        if not s:
            return 0.0
        try:
            s = str(s).replace(" ", "").replace("\xa0", "")
            for code in ["PKR", "CAD", "GBP", "EUR", "AUD", "INR"]:
                if code in s:
                    s = s.replace(code, "")
                    break
            if "," in s and "." in s:
                s = s.replace(",", "") if s.find(",") < s.find(".") else s.replace(".", "").replace(",", ".")
            elif "," in s:
                parts = s.split(",")
                s = s.replace(",", ".") if len(parts) == 2 and len(parts[1]) <= 2 else s.replace(",", "")
            return float(re.sub(r"[^\d.]", "", s) or 0)
        except ValueError:
            return 0.0

    @staticmethod
    def _detect_currency(text):
        for code in ["PKR", "CAD", "GBP", "EUR", "AUD", "INR"]:
            if code in (text or ""):
                return code
        return None

    def _parse_jsonld_from_soup(self, soup, url):
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = json.loads(script.string.strip())
                items = raw if isinstance(raw, list) else raw.get("@graph", [raw])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if "Product" not in (item.get("@type", "") if isinstance(item.get("@type"), list) else [item.get("@type", "")]):
                        continue
                    name = item.get("name")
                    if not name:
                        continue
                    img = item.get("image")
                    if isinstance(img, list):
                        img = img[0]
                    if isinstance(img, dict):
                        img = img.get("url") or ""
                    if not isinstance(img, str):
                        img = ""
                    price = None
                    currency = "USD"
                    offers = item.get("offers")
                    if isinstance(offers, dict):
                        price = offers.get("price")
                        currency = offers.get("priceCurrency", "USD")
                    elif isinstance(offers, list):
                        for o in offers:
                            if isinstance(o, dict) and o.get("price"):
                                price = o.get("price")
                                currency = o.get("priceCurrency", "USD")
                                break
                    if price is not None:
                        return {
                            "name": name,
                            "price": self._extract_price(str(price)),
                            "currency": currency or "USD",
                            "main_image_url": urljoin(url, img) if img else "",
                        }
            except Exception:
                pass
        return None

    def _parse_meta_from_soup(self, soup, url):
        data = {"name": "", "price": 0.0, "currency": "USD", "main_image_url": ""}
        for prop in ["og:title", "twitter:title"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                data["name"] = m["content"]
                break
        for prop in ["product:price:amount", "og:price:amount"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                data["price"] = self._extract_price(m["content"])
                break
        for prop in ["product:price:currency", "og:price:currency"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                data["currency"] = m["content"]
                break
        for prop in ["og:image", "twitter:image"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                data["main_image_url"] = urljoin(url, m["content"])
                break
        return data if data["name"] or data["price"] > 0 else None

    def _parse_generic_from_soup(self, soup, url):
        data = {"name": "", "price": 0.0, "currency": "USD", "main_image_url": ""}
        h1 = soup.find("h1")
        data["name"] = h1.get_text().strip() if h1 else (soup.find("title").get_text().strip() if soup.find("title") else "")
        if data["name"]:
            sep = re.search(r"\s[–\-—|]\s", data["name"])
            if sep:
                data["name"] = data["name"][:sep.start()].strip()

        price_pat = re.compile(r"^\s*[$€£¥₽]?\s*[\d,]+\.\d{2}\s*$")
        for tag in soup.find_all(class_=re.compile(r"(^|[\s-])price($|[\s-])", re.I)):
            txt = tag.get_text().strip()
            if price_pat.match(txt):
                data["price"] = self._extract_price(txt)
                c = self._detect_currency(txt)
                if c:
                    data["currency"] = c
                break

        for tag in soup.find_all("img", class_=re.compile(r"(^|[\s-])product($|[\s-])", re.I)):
            src = tag.get("src") or tag.get("data-src")
            if src and not src.startswith("data:"):
                data["main_image_url"] = urljoin(url, src)
                break
        if not data["main_image_url"]:
            for tag in soup.find_all("img", limit=10):
                src = tag.get("src") or tag.get("data-src")
                if src and "logo" not in src.lower() and not src.startswith("data:"):
                    data["main_image_url"] = urljoin(url, src)
                    break
        return data if data["name"] else None
