import os
import base64
import json
import logging
import tempfile
from dotenv import load_dotenv
import pytz
import contextvars
from contextlib import contextmanager
from functools import wraps

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
USER_TIMEZONE = os.getenv("USER_TIMEZONE", "Asia/Kolkata").strip()

LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
LINKEDIN_PERSON_URN = os.getenv("LINKEDIN_PERSON_URN", "").strip()

ADMIN_USER_ID = 5484600217
OPEN_ACCESS = os.getenv("OPEN_ACCESS", "false").lower() in ("true", "1", "yes")
SHEETS_DURABLE_STORAGE = os.getenv("SHEETS_DURABLE_STORAGE", "false").lower() in ("true", "1", "yes")

DATA_DIR = os.path.abspath(os.getenv("JARVIS_DATA_DIR", os.path.dirname(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)
# Remember this before service imports create their empty tables.
MISSING_DATABASES = {
    name for name in ("notes", "tasks", "habits", "expenses", "books", "reminders")
    if not os.path.exists(os.path.join(DATA_DIR, f"{name}.db"))
}

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

@contextmanager
def user_context(user_id: int, user_name: str = "User"):
    id_token = _current_user_id_var.set(user_id)
    name_token = _current_user_name_var.set(user_name)
    try:
        yield
    finally:
        _current_user_name_var.reset(name_token)
        _current_user_id_var.reset(id_token)

def require_admin(func):
    """Enforce private integration access at the service boundary, including AI tools."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not is_admin(get_current_user_id()):
            raise PermissionError("This integration is restricted to Revanth Sir.")
        return func(*args, **kwargs)
    return wrapper

def get_current_user_id() -> int:
    return _current_user_id_var.get()

def resolve_user_id(user_id: int = None) -> int:
    # Keep the legacy parameter for tool compatibility, but never trust it as identity.
    # Trusted scheduled jobs select the recipient with user_context instead.
    return get_current_user_id()

def get_current_user_name() -> str:
    return _current_user_name_var.get()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID

def is_authorized(user_id: int) -> bool:
    if OPEN_ACCESS:
        return True
    return user_id in ALLOWED_USER_IDS or user_id == ADMIN_USER_ID

def install_google_token(raw: str, token_path: str) -> bool:
    """Validate cloud credentials before atomically replacing a working token file."""
    temp_path = None
    try:
        content = raw if raw.lstrip().startswith("{") else base64.b64decode(raw, validate=True).decode("utf-8")
        token = json.loads(content)
        if not isinstance(token, dict) or not all(token.get(key) for key in ("refresh_token", "client_id", "client_secret")):
            raise ValueError("Invalid authorized-user credentials")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(token_path),
                                         prefix="google-token-", suffix=".tmp", delete=False) as f:
            temp_path = f.name
            json.dump(token, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, token_path)
        return True
    except Exception:
        # Credentials and decoder errors can contain secrets; do not log their values.
        logging.getLogger(__name__).error("GOOGLE_TOKEN_JSON could not be installed; existing token preserved.")
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
if GOOGLE_TOKEN_JSON:
    install_google_token(GOOGLE_TOKEN_JSON, os.path.join(os.path.dirname(__file__), "token.json"))

def get_tz():
    try:
        return pytz.timezone(USER_TIMEZONE)
    except Exception:
        return pytz.timezone("Asia/Kolkata")
