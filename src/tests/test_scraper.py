from src.scraper import CustomScraper


def test_extract_price():
    s = CustomScraper()
    assert s._extract_price("$19.99") == 19.99
    assert s._extract_price("PKR 1,500.00") == 1500.0
    assert s._extract_price("") == 0.0
