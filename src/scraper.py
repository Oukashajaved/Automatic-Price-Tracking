import json
import random
import re
import threading
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

_playwright_lock = threading.Lock()

def fetch_rendered_html(url: str) -> str:
    import asyncio
    import nest_asyncio
    from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

    with _playwright_lock:
        html_content = []

        async def run_crawler():
            crawler = PlaywrightCrawler(
                max_requests_per_crawl=1,
                headless=True,
            )
            @crawler.router.default_handler
            async def request_handler(context: PlaywrightCrawlingContext):
                await context.page.wait_for_timeout(6000)
                html = await context.page.content()
                html_content.append(html)
                
            await crawler.run([url])

        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                nest_asyncio.apply()
                
            loop.run_until_complete(run_crawler())
        except Exception as e:
            print(f"[Scraper] Crawlee failed for {url}: {e}")

        return html_content[0] if html_content else ""


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
        self._soup_cache = {}

    def scrape_url(self, url):
        self._soup_cache.clear()
        extracted = None
        self._force_playwright = False
        
        # 1. First attempt: Standard requests
        for method_name in ["_from_jsonld", "_from_microdata", "_from_meta", "_from_generic"]:
            try:
                data = getattr(self, method_name)(url)
                if data and data.get("name"):
                    if data.get("price", 0.0) > 0.0:
                        extracted = data
                        break
                    else:
                        extracted = data
            except Exception as e:
                print(f"[Scraper] Method {method_name} failed: {e}")
                
        # 2. Dynamic fallback: if price is 0.0 or not found, use Playwright
        if not extracted or extracted.get("price", 0.0) == 0.0:
            print(f"[Scraper] Price was 0.0 or not found. Retrying {url} through Playwright...")
            self._force_playwright = True
            self._soup_cache.clear()
            for method_name in ["_from_jsonld", "_from_microdata", "_from_meta", "_from_generic"]:
                try:
                    data = getattr(self, method_name)(url)
                    if data and data.get("name"):
                        extracted = data
                        if data.get("price", 0.0) > 0.0:
                            break
                except Exception as e:
                    print(f"[Scraper] Playwright method {method_name} failed: {e}")
                    
        if not extracted:
            raise Exception(f"Could not scrape: {url}")
            
        # Clean up and normalize fields
        if not extracted.get("images"):
            extracted["images"] = [extracted["main_image_url"]] if extracted.get("main_image_url") else []
        if not extracted.get("brand"):
            extracted["brand"] = ""
        if not extracted.get("seller"):
            extracted["seller"] = ""
        if not extracted.get("rating"):
            extracted["rating"] = 0.0
        if not extracted.get("review_count"):
            extracted["review_count"] = 0
        if not extracted.get("condition"):
            extracted["condition"] = "New"
        if not extracted.get("shipping"):
            extracted["shipping"] = "Calculated at checkout"
        if not extracted.get("description"):
            extracted["description"] = ""
        if not extracted.get("specs"):
            extracted["specs"] = {}
            
        return {"extract": extracted}

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
                        
                    # Extract description
                    desc = item.get("description", "")
                    
                    # Extract brand
                    brand_data = item.get("brand")
                    brand = ""
                    if isinstance(brand_data, dict):
                        brand = brand_data.get("name", "")
                    elif isinstance(brand_data, str):
                        brand = brand_data
                    elif isinstance(brand_data, list) and brand_data:
                        first_brand = brand_data[0]
                        brand = first_brand.get("name", "") if isinstance(first_brand, dict) else str(first_brand)
                        
                    # Extract images
                    main_img = ""
                    images = []
                    img_data = item.get("image")
                    if img_data:
                        if isinstance(img_data, list):
                            for im in img_data:
                                if isinstance(im, dict):
                                    u = im.get("url") or im.get("contentUrl")
                                    if u:
                                        images.append(urljoin(url, u))
                                elif isinstance(im, str):
                                    images.append(urljoin(url, im))
                        elif isinstance(img_data, dict):
                            u = img_data.get("url") or img_data.get("contentUrl")
                            if u:
                                images.append(urljoin(url, u))
                        elif isinstance(img_data, str):
                            images.append(urljoin(url, img_data))
                    if images:
                        main_img = images[0]
                        
                    # Extract ratings
                    rating = 0.0
                    review_count = 0
                    agg_rating = item.get("aggregateRating")
                    if isinstance(agg_rating, dict):
                        try:
                            rating = float(agg_rating.get("ratingValue") or 0.0)
                        except:
                            pass
                        try:
                            review_count = int(agg_rating.get("reviewCount") or agg_rating.get("ratingCount") or 0)
                        except:
                            pass
                        
                    # Extract offers (price, currency, seller, condition, shipping)
                    price = 0.0
                    currency = "USD"
                    seller = ""
                    condition = ""
                    shipping = ""
                    
                    offers = item.get("offers")
                    offer_list = []
                    if isinstance(offers, dict):
                        offer_list = [offers]
                    elif isinstance(offers, list):
                        offer_list = offers
                        
                    for o in offer_list:
                        if not isinstance(o, dict):
                            continue
                        p = o.get("price")
                        if p:
                            price = self._extract_price(str(p))
                        curr = o.get("priceCurrency")
                        if curr:
                            currency = curr
                            
                        # Seller
                        sel = o.get("seller")
                        if isinstance(sel, dict):
                            seller = sel.get("name", "")
                        elif isinstance(sel, str):
                            seller = sel
                            
                        # Condition
                        cond = o.get("itemCondition")
                        if cond:
                            condition = str(cond).split("/")[-1].replace("Condition", "")
                            
                        # Shipping
                        ship_details = o.get("shippingDetails")
                        if isinstance(ship_details, dict):
                            rate = ship_details.get("shippingRate", {}).get("value")
                            if rate is not None:
                                shipping = f"${rate}" if float(rate) > 0 else "Free Shipping"
                        
                        if price > 0:
                            break # Found a valid offer
                            
                    # Extract specs / additional properties
                    specs = {}
                    add_props = item.get("additionalProperty")
                    if isinstance(add_props, list):
                        for prop in add_props:
                            if isinstance(prop, dict) and prop.get("name") and prop.get("value"):
                                specs[prop["name"]] = prop["value"]
                                
                    if name:
                        return {
                            "name": name,
                            "price": price,
                            "currency": currency or "USD",
                            "main_image_url": main_img,
                            "images": images,
                            "brand": brand,
                            "seller": seller,
                            "rating": rating,
                            "review_count": review_count,
                            "condition": condition,
                            "shipping": shipping,
                            "description": desc,
                            "specs": specs
                        }
            except Exception as e:
                print(f"[Scraper] JSON-LD parse error: {e}")
        return None

    def _from_microdata(self, url):
        soup = self._soup(url)
        if not soup:
            return None
        data = {
            "name": "", "price": 0.0, "currency": "USD", "main_image_url": "",
            "images": [], "brand": "", "seller": "", "rating": 0.0,
            "review_count": 0, "condition": "New", "shipping": "", "description": "", "specs": {}
        }

        name_el = soup.find(itemprop="name")
        if name_el:
            data["name"] = name_el.get("content") or name_el.get_text().strip()

        price_el = soup.find(itemprop="price")
        if price_el:
            data["price"] = self._extract_price(price_el.get("content") or price_el.get_text())
            curr_el = soup.find(itemprop="priceCurrency")
            if curr_el:
                data["currency"] = curr_el.get("content") or curr_el.get_text()

        img_els = soup.find_all(itemprop="image")
        for img_el in img_els:
            src = img_el.get("src") or img_el.get("content") or img_el.get("href")
            if src:
                data["images"].append(urljoin(url, src))
        if data["images"]:
            data["main_image_url"] = data["images"][0]

        brand_el = soup.find(itemprop="brand")
        if brand_el:
            data["brand"] = brand_el.get("content") or brand_el.get_text().strip()

        seller_el = soup.find(itemprop="seller")
        if seller_el:
            data["seller"] = seller_el.get("content") or seller_el.get_text().strip()

        rating_el = soup.find(itemprop="ratingValue")
        if rating_el:
            try:
                data["rating"] = float(rating_el.get("content") or rating_el.get_text() or 0.0)
            except:
                pass

        reviews_el = soup.find(itemprop="reviewCount")
        if reviews_el:
            try:
                data["review_count"] = int(reviews_el.get("content") or reviews_el.get_text() or 0)
            except:
                pass

        cond_el = soup.find(itemprop="itemCondition")
        if cond_el:
            data["condition"] = (cond_el.get("content") or cond_el.get_text() or "").split("/")[-1].replace("Condition", "")

        desc_el = soup.find(itemprop="description")
        if desc_el:
            data["description"] = desc_el.get("content") or desc_el.get_text().strip()

        return data if data["name"] or data["price"] > 0 else None

    def _from_meta(self, url):
        soup = self._soup(url)
        if not soup:
            return None
        data = {
            "name": "", "price": 0.0, "currency": "USD", "main_image_url": "",
            "images": [], "brand": "", "seller": "", "rating": 0.0,
            "review_count": 0, "condition": "New", "shipping": "", "description": "", "specs": {}
        }

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
                data["images"].append(urljoin(url, m["content"]))
                break
        if data["images"]:
            data["main_image_url"] = data["images"][0]

        for prop in ["product:brand", "og:brand"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                data["brand"] = m["content"]
                break

        for prop in ["product:condition", "og:condition"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                data["condition"] = m["content"]
                break

        m = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        if m and m.get("content"):
            data["description"] = m["content"]

        return data if data["name"] or data["price"] > 0 else None

    def _from_generic(self, url):
        soup = self._soup(url)
        if not soup:
            return None
        data = {
            "name": "", "price": 0.0, "currency": "USD", "main_image_url": "",
            "images": [], "brand": "", "seller": "", "rating": 0.0,
            "review_count": 0, "condition": "New", "shipping": "", "description": "", "specs": {}
        }

        h1 = soup.find("h1")
        if h1:
            data["name"] = h1.get_text().strip()
        if not data["name"]:
            tt = soup.find("title")
            if tt:
                t = tt.get_text().strip()
                sep = re.search(r"\s[–\-—|]\s", t)
                data["name"] = t[:sep.start()].strip() if sep else t

        # Broad price extraction patterns
        candidates = []
        for tag in soup.find_all(lambda t: t.name in ["span", "div", "p", "b", "strong", "bdi"] and (t.get("class") or t.get("id"))):
            cls = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
            if "price" in cls.lower():
                txt = tag.get_text().strip()
                m = re.search(r'([$€£¥₽]|PKR|Rs\.?)?\s*(\d{1,3}(?:[,\s]?\d{3})*(?:\.\d{2})?)', txt)
                if m:
                    val = self._extract_price(m.group(0))
                    if val > 0:
                        candidates.append((val, tag))

        if not candidates:
            for tag in soup.find_all(string=True):
                txt = tag.strip()
                if len(txt) < 30 and re.search(r'([$€£¥₽]|PKR|Rs\.?)\s*(\d{1,3}(?:[,\s]?\d{3})*(?:\.\d{2})?)', txt):
                    val = self._extract_price(txt)
                    if val > 0:
                        candidates.append((val, tag.parent))

        if candidates:
            data["price"] = candidates[0][0]
            txt = candidates[0][1].get_text()
            data["currency"] = self._detect_currency(txt)

        img_tags = soup.find_all("img", class_=re.compile(r"(^|[\s-])product($|[\s-])", re.I))
        if not img_tags:
            img_tags = soup.find_all("img", limit=5)
        for tag in img_tags:
            src = tag.get("src") or tag.get("data-src")
            if src and "logo" not in src.lower() and not src.startswith("data:"):
                data["images"].append(urljoin(url, src))
        if data["images"]:
            data["main_image_url"] = data["images"][0]

        return data if data["name"] else None

    def _soup(self, url):
        if url not in self._soup_cache:
            html = self._fetch(url)
            self._soup_cache[url] = BeautifulSoup(html, "html.parser") if html else None
        return self._soup_cache[url]

    def _fetch(self, url):
        if getattr(self, "_force_playwright", False):
            print(f"[Scraper] Routing {url} through Playwright...")
            return fetch_rendered_html(url)

        ua = random.choice(self.__USER_AGENTS)
        self._session.headers.update({
            "User-Agent": ua,
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        parsed = urlparse(url)
        
        # Try standard requests first
        html = ""
        try:
            self._session.get(f"{parsed.scheme}://{parsed.netloc}", headers={"User-Agent": ua}, timeout=10)
            resp = self._session.get(url, timeout=20)
            if resp.status_code == 200 and "captcha" not in resp.text.lower() and "are you a human" not in resp.text.lower():
                html = resp.text
            elif resp.status_code in (403, 503):
                time.sleep(2)
                resp = requests.get(
                    url,
                    headers={
                        "User-Agent": ua,
                        "Accept": "text/html,*/*",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": "https://www.google.com/",
                    },
                    timeout=20,
                )
                if resp.status_code == 200 and "captcha" not in resp.text.lower() and "are you a human" not in resp.text.lower():
                    html = resp.text
        except Exception as e:
            print(f"[Scraper] Standard request failed: {e}")
            
        # Fall back to Playwright if standard requests failed or returned CAPTCHA
        if not html:
            print(f"[Scraper] Routing {url} through Playwright...")
            html = fetch_rendered_html(url)
            
        return html

    @staticmethod
    def _extract_price(s):
        if not s:
            return 0.0
        try:
            s = str(s).replace(" ", "").replace("\xa0", "")
            for code in ["PKR", "CAD", "GBP", "EUR", "AUD", "INR", "USD"]:
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
        if not text:
            return "USD"
        text = text.upper()
        if "PKR" in text or "RS" in text:
            return "PKR"
        for code in ["CAD", "GBP", "EUR", "AUD", "INR", "USD"]:
            if code in text:
                return code
        if "$" in text:
            return "USD"
        if "€" in text:
            return "EUR"
        if "£" in text:
            return "GBP"
        return "USD"
