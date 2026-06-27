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
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import json
    
    # 1. Search all domains on Yahoo in parallel
    def fetch_urls(site_name, domain):
        try:
            return site_name, search_site_urls(query, domain, max_pages)
        except Exception as e:
            print(f"[Search] Yahoo search error for {site_name}: {e}")
            return site_name, []

    if progress_callback:
        progress_callback("Searching for product links on search engine...")
        
    site_to_urls = {}
    with ThreadPoolExecutor(max_workers=max(len(domains), 1)) as executor:
        futures = {executor.submit(fetch_urls, name, dom): name for name, dom in domains.items()}
        for future in as_completed(futures):
            name, urls = future.result()
            site_to_urls[name] = urls
            
    # 2. Gather all tasks
    all_tasks = []
    for site_name, urls in site_to_urls.items():
        for i, url in enumerate(urls[:10]):
            all_tasks.append((site_name, url, i))
            
    if not all_tasks:
        return {}
        
    if progress_callback:
        progress_callback(f"Found {len(all_tasks)} products. Scraping details concurrently...")

    results = {name: [] for name in domains.keys()}
    
    def scrape_single_task(task):
        site_name, url, idx = task
        # Use a fresh scraper instance in each thread to ensure thread-safety
        scraper = CustomScraper()
        try:
            data = scraper.scrape_url(url)["extract"]
            return site_name, {
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
            }
        except Exception as e:
            print(f"[Search] Error scraping {url}: {e}")
            return site_name, None

    # Limit max_workers to 4 to balance concurrent speed and system resources
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(scrape_single_task, task): task for task in all_tasks}
        for future in as_completed(futures):
            site_name, res_dict = future.result()
            if res_dict:
                results[site_name].append(res_dict)
                if progress_callback:
                    progress_callback(f"Scraped: {res_dict['name'][:40]}... ({site_name})")

    # Remove empty results
    return {k: v for k, v in results.items() if v}
