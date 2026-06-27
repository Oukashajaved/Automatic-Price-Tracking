import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote

_PRODUCT_SUBPATHS = {
    "amazon.com": "amazon.com/dp",
    "ebay.com": "ebay.com/itm",
    "walmart.com": "walmart.com/ip",
    "bestbuy.com": "bestbuy.com/site",
    "target.com": "target.com/p",
    "etsy.com": "etsy.com/listing",
    "newegg.com": "newegg.com/p",
    "aliexpress.com": "aliexpress.com/item",
    "homedepot.com": "homedepot.com/p",
    "wayfair.com": "wayfair.com/furniture/pdp",
}

def search_site_urls(query: str, domain: str, max_pages: int = 1) -> list[str]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    
    urls = []
    
    q_site = domain
    for d_key, subpath in _PRODUCT_SUBPATHS.items():
        if d_key in domain.lower():
            q_site = subpath
            break
            
    q_str = f"site:{q_site} {query}"
    
    exclude_patterns = [
        "/search", "/sch/", "/category", "/c/kp/", "?k=", "?st=", "?d=",
        "/collections/", "/shop/", "/pages/", "/cart", "/login", "/join",
        "/help", "/about", "/terms", "/privacy", "/contact", "vertical-srp",
        "p/pl?d="
    ]
    
    for page in range(max_pages):
        offset = page * 10 + 1
        url = f"https://search.yahoo.com/search?q={requests.utils.quote(q_str)}&b={offset}"
        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                break
                
            soup = BeautifulSoup(r.text, "html.parser")
            page_urls = []
            
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "r.search.yahoo.com" in href:
                    m = re.search(r'/RU=([^/]+)/', href)
                    if m:
                        real_url = unquote(m.group(1))
                        if domain.lower() in real_url.lower():
                            clean_url = real_url.split("?")[0] if "?" in real_url else real_url
                            if not any(pattern in clean_url.lower() for pattern in exclude_patterns):
                                if clean_url not in urls and clean_url not in page_urls:
                                    page_urls.append(clean_url)
                                    
            if not page_urls:
                break
            urls.extend(page_urls)
        except Exception as e:
            print(f"[Yahoo Search] Error on page {page} for {domain}: {e}")
            break
            
    return urls


def search_all_generic(query: str, domains: dict[str, str], max_pages: int = 1, progress_callback=None) -> dict[str, list[dict]]:
    """
    domains: dict of {site_display_name: domain_name} (e.g. {"Amazon": "amazon.com"})
    """
    from src.scraper import CustomScraper
    import json
    
    site_to_urls = {}
    for site_name, domain in domains.items():
        try:
            site_to_urls[site_name] = search_site_urls(query, domain, max_pages)
        except Exception as e:
            print(f"[Search] Yahoo search error for {site_name}: {e}")
            site_to_urls[site_name] = []
            
    # 2. Gather all tasks
    urls_to_scrape = []
    task_map = []  # List of (site_name, url)
    for site_name, urls in site_to_urls.items():
        for url in urls[:10]:
            urls_to_scrape.append(url)
            task_map.append((site_name, url))
            
    if not urls_to_scrape:
        return {}
        
    if progress_callback:
        progress_callback(f"Found {len(urls_to_scrape)} products. Scraping details in batch...")

    scraper = CustomScraper()
    batch_results = scraper.scrape_urls_batch(urls_to_scrape)
    
    results = {name: [] for name in domains.keys()}
    for (site_name, url), data in zip(task_map, batch_results):
        if data and data.get("name"):
            results[site_name].append({
                "url": url,
                "name": data["name"],
                "price": data["price"],
                "currency": data.get("currency", "USD"),
                "main_image_url": data.get("main_image_url", ""),
                "images": json.dumps(data.get("images", [])),
                "brand": data.get("brand", ""),
                "seller": data.get("seller", "") or site_name,
                "seller_rating": str(data.get("rating", 0.0)),
                "review_count": int(data.get("review_count", 0)),
                "condition": data.get("condition", "New"),
                "shipping": data.get("shipping", "Calculated at checkout"),
                "site": site_name,
                "description": data.get("description", ""),
                "specs": json.dumps(data.get("specs", {}))
            })
            if progress_callback:
                progress_callback(f"Scraped: {data['name'][:40]}... ({site_name})")

    # Remove empty results
    return {k: v for k, v in results.items() if v}
