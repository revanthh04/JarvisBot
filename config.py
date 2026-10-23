import os
from dotenv import load_dotenv
import pytz

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "Asia/Kolkata").strip()

raw_ids = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS = []
if raw_ids:
    for uid in raw_ids.replace(";", ",").split(","):
        uid = uid.strip()
        if uid.isdigit():
            ALLOWED_USER_IDS.append(int(uid))

def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True  # If no user IDs set, open (not recommended)
    return user_id in ALLOWED_USER_IDS

def get_tz():
    try:
        return pytz.timezone(USER_TIMEZONE)
    except Exception:
        return pytz.timezone("Asia/Kolkata")
