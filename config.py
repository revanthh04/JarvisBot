import os
import base64
from dotenv import load_dotenv
import pytz
import contextvars

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "Asia/Kolkata").strip()

ADMIN_USER_ID = 5484600217
OPEN_ACCESS = os.getenv("OPEN_ACCESS", "true").lower() in ("true", "1", "yes")

raw_ids = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS = []
if raw_ids:
    for uid in raw_ids.replace(";", ",").split(","):
        uid = uid.strip()
        if uid.isdigit():
            ALLOWED_USER_IDS.append(int(uid))

# Context-isolated user state for multi-user concurrency
_current_user_id_var = contextvars.ContextVar("current_user_id", default=ADMIN_USER_ID)
_current_user_name_var = contextvars.ContextVar("current_user_name", default="Revanth Sir")

def set_current_user(user_id: int, user_name: str = "User"):
    _current_user_id_var.set(user_id)
    _current_user_name_var.set(user_name)

def get_current_user_id() -> int:
    return _current_user_id_var.get()

def resolve_user_id(user_id: int = None) -> int:
    curr = get_current_user_id()
    if user_id is None:
        return curr
    try:
        uid_int = int(user_id)
        if uid_int < 100000:  # Telegram IDs are 8-10 digits; filter out LLM hallucinated IDs like 1 or 0
            return curr
        if is_authorized(uid_int):
            return uid_int
    except Exception:
        pass
    return curr

def get_current_user_name() -> str:
    return _current_user_name_var.get()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID

def is_authorized(user_id: int) -> bool:
    if OPEN_ACCESS:
        return True
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS or user_id == ADMIN_USER_ID

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

def get_tz():
    try:
        return pytz.timezone(USER_TIMEZONE)
    except Exception:
        return pytz.timezone("Asia/Kolkata")
