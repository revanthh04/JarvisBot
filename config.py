import os
import base64
from dotenv import load_dotenv
import pytz

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "Asia/Kolkata").strip()

raw_ids = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS = []
if raw_ids:
    for uid in raw_ids.replace(";", ",").split(","):
        uid = uid.strip()
        if uid.isdigit():
            ALLOWED_USER_IDS.append(int(uid))

# Load Google token from environment variable for cloud deployment
GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
if GOOGLE_TOKEN_JSON:
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    try:
        content = None
        if GOOGLE_TOKEN_JSON.startswith("{"):
            content = GOOGLE_TOKEN_JSON
        else:
            try:
                content = base64.b64decode(GOOGLE_TOKEN_JSON).decode("utf-8")
            except Exception:
                content = GOOGLE_TOKEN_JSON
        if content:
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(content)
    except Exception:
        pass

def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True  # If no user IDs set, open (not recommended)
    return user_id in ALLOWED_USER_IDS

def get_tz():
    try:
        return pytz.timezone(USER_TIMEZONE)
    except Exception:
        return pytz.timezone("Asia/Kolkata")
