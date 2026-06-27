import os  # ponytail: os.getenv is built-in, no dotenv dep needed
from src.db import get_setting


def get_discord_webhook():
    return get_setting("discord_webhook_url") or os.getenv("DISCORD_WEBHOOK_URL", "")

def get_drop_threshold():
    val = get_setting("drop_threshold")
    if val:
        return float(val)
    return float(os.getenv("PRICE_DROP_THRESHOLD", "0.05"))

def get_groq_api_key():
    return get_setting("groq_api_key") or os.getenv("GROQ_API_KEY", "")

def get_serper_api_key():
    return get_setting("serper_api_key") or os.getenv("SERPER_API_KEY", "")
