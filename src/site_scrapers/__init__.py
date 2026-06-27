from .search import search_all_generic

_PREDEFINED_SITES = {
    "Amazon": "amazon.com",
    "eBay": "ebay.com",
    "Walmart": "walmart.com",
    "Best Buy": "bestbuy.com",
    "Newegg": "newegg.com",
    "Target": "target.com",
    "Home Depot": "homedepot.com",
    "Etsy": "etsy.com",
    "AliExpress": "aliexpress.com",
    "Costco": "costco.com",
    "Wayfair": "wayfair.com"
}


def available_sites() -> list[str]:
    return list(_PREDEFINED_SITES.keys())


def search_all(query: str, sites: list[str] | None = None, custom_domains: list[str] | None = None, max_pages: int = 1, progress_callback=None) -> dict[str, list[dict]]:
    domains = {}
    if sites:
        for s in sites:
            if s in _PREDEFINED_SITES:
                domains[s] = _PREDEFINED_SITES[s]
                
    if custom_domains:
        for cd in custom_domains:
            cd = cd.strip()
            if cd:
                display_name = cd.replace("www.", "").split(".")[0].capitalize()
                domains[display_name] = cd
                
    if not domains:
        domains = {"eBay": "ebay.com", "Newegg": "newegg.com"}
        
    return search_all_generic(query, domains, max_pages=max_pages, progress_callback=progress_callback)
