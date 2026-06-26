from src.notifications import send_price_alert


def test():
    send_price_alert("Test Product", 99.99, 79.99, "https://www.amazon.com/dp/B09HMV6K1W")


if __name__ == "__main__":
    test()
