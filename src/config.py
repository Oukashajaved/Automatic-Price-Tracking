import os
from dotenv import load_dotenv
from src.db import get_setting

load_dotenv()


def get_discord_webhook():
    return get_setting("discord_webhook_url") or os.getenv("DISCORD_WEBHOOK_URL", "")

def get_drop_threshold():
    val = get_setting("drop_threshold")
    if val:
        return float(val)
    return float(os.getenv("PRICE_DROP_THRESHOLD", "0.05"))
