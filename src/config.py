import os
from pathlib import Path
from src.db import get_setting

# ponytail: manual .env loader, no dotenv dep
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def get_discord_webhook():
    return get_setting("discord_webhook_url") or os.getenv("DISCORD_WEBHOOK_URL", "")

def get_drop_threshold():
    val = get_setting("drop_threshold")
    if val:
        return float(val)
    return float(os.getenv("PRICE_DROP_THRESHOLD", "0.05"))

def get_groq_api_key():
    return get_setting("groq_api_key") or os.getenv("GROQ_API_KEY", "")
