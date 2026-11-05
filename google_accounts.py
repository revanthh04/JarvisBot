"""Per-Telegram-user OAuth credentials. No guest fallback to the owner's token.

Cloud connections require PostgreSQL and a stable Fernet encryption key. Local
SQLite is supported only for development; it is refused on Render. OAuth state
and PKCE are single use; a second confirmation in Telegram binds the identity.
"""
import base64
from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlparse

import config

SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive.file"]
_lock = threading.RLock()


class NotConnected(PermissionError):
    pass


def _cipher():
    from cryptography.fernet import Fernet
    return Fernet(os.environ["GOOGLE_ACCOUNTS_ENCRYPTION_KEY"].encode())


def _encrypt(uid, value):
    return _cipher().encrypt(json.dumps({"uid": uid, "value": value}).encode()).decode()


def _decrypt(uid, value):
    data = json.loads(_cipher().decrypt(value.encode()))
    if data["uid"] != uid:
        raise NotConnected("Google account owner mismatch")
    return data["value"]


@contextmanager
def _db():
    dsn = os.getenv("GOOGLE_ACCOUNTS_DATABASE_URL", "").strip()
    local = os.getenv("GOOGLE_ACCOUNTS_SQLITE", "").strip()
    if dsn:
        import psycopg
        conn = psycopg.connect(dsn, sslmode="require", connect_timeout=10)
        def execute(sql, args=()):
            return conn.execute(sql, args)
    elif local and not os.getenv("RENDER"):
        conn = sqlite3.connect(local, timeout=10)
        def execute(sql, args=()):
            return conn.execute(sql.replace("%s", "?"), args)
    else:
        raise NotConnected("Personal Google connections are not configured yet")
    try:
        execute("CREATE TABLE IF NOT EXISTS google_accounts (uid BIGINT PRIMARY KEY, token TEXT NOT NULL, email TEXT NOT NULL, sheet_id TEXT NOT NULL DEFAULT '', disabled INTEGER NOT NULL DEFAULT 0)")
        execute("CREATE TABLE IF NOT EXISTS google_oauth_pending (state_hash TEXT PRIMARY KEY, uid BIGINT NOT NULL, verifier TEXT NOT NULL, expires BIGINT NOT NULL, confirmation_hash TEXT NOT NULL DEFAULT '', token TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '')")
        yield execute
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _client():
    raw = os.environ["GOOGLE_OAUTH_WEB_CLIENT_JSON"]
    data = json.loads(raw if raw.lstrip().startswith("{") else base64.b64decode(raw).decode())
    web = data["web"]
    if not all(web.get(k) for k in ("client_id", "client_secret", "auth_uri", "token_uri")):
        raise ValueError("Invalid web OAuth client")
    if web["auth_uri"] != "https://accounts.google.com/o/oauth2/auth" or web["token_uri"] != "https://oauth2.googleapis.com/token":
        raise ValueError("Only Google OAuth endpoints are supported")
    return data


def _redirect():
    url = os.environ["GOOGLE_OAUTH_REDIRECT_URI"].strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.path != "/google/callback" or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("A registered HTTPS callback is required")
    return url


def setup_ready():
    try:
        _client()
        _redirect()
        _cipher()
        return bool(os.getenv("GOOGLE_ACCOUNTS_DATABASE_URL") or
                    (os.getenv("GOOGLE_ACCOUNTS_SQLITE") and not os.getenv("RENDER")))
    except Exception:
        return False


def begin_connection():
    uid = config.get_current_user_id()
    if not config.is_authorized(uid):
        raise PermissionError("User is not approved for YoBot")
    if not setup_ready():
        return "Personal Google sign-in is being set up. The owner must configure the secure account database and Google web sign-in first."
    from google_auth_oauthlib.flow import Flow
    state = secrets.token_urlsafe(32)
    flow = Flow.from_client_config(_client(), scopes=SCOPES, state=state,
                                  redirect_uri=_redirect(), autogenerate_code_verifier=True)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    with _db() as execute:
        execute("DELETE FROM google_oauth_pending WHERE uid = %s OR expires < %s", (uid, int(time.time())))
        execute("INSERT INTO google_oauth_pending (state_hash,uid,verifier,expires) VALUES (%s,%s,%s,%s)",
                (_hash(state), uid, _encrypt(uid, flow.code_verifier), int(time.time()) + 600))
    return ("Open this personal Google sign-in link within 10 minutes:\n" + url +
            "\nAfter sign-in, return here with the confirmation code shown in your browser. Never share this link or code.")


def oauth_callback(query):
    """Return only plain status text. Never log callback URLs or tokens."""
    state = query.get("state", [""])[0]
    if not state or len(state) > 256:
        return "This sign-in link is invalid. Return to Telegram and use /connectgoogle."
    with _db() as execute:
        row = execute("DELETE FROM google_oauth_pending WHERE state_hash = %s AND confirmation_hash = '' RETURNING uid,verifier,expires", (_hash(state),)).fetchone()
    if not row or row[2] < time.time() or not config.is_authorized(row[0]):
        return "This sign-in link has expired or was already used. Return to Telegram and use /connectgoogle."
    if query.get("error"):
        return "Google connection cancelled. Nothing was connected."
    code = query.get("code", [""])[0]
    if not code:
        return "No authorization was received. Start again in Telegram."
    uid, verifier, expires = row
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client(), scopes=SCOPES, state=state,
                                  code_verifier=_decrypt(uid, verifier), redirect_uri=_redirect())
    flow.fetch_token(code=code, timeout=20)
    creds = flow.credentials
    if not creds.refresh_token or not set(SCOPES).issubset(set(creds.granted_scopes or creds.scopes or [])):
        return "Google permissions were incomplete. Nothing was connected. Start again and approve the requested services."
    import requests
    response = requests.get("https://openidconnect.googleapis.com/v1/userinfo",
                            headers={"Authorization": "Bearer " + creds.token}, timeout=20)
    response.raise_for_status()
    profile = response.json()
    if not profile.get("email_verified") or not profile.get("email"):
        return "Google account identity could not be verified. Nothing was connected."
    confirmation = secrets.token_urlsafe(18)
    with _db() as execute:
        execute("INSERT INTO google_oauth_pending (state_hash,uid,verifier,expires,confirmation_hash,token,email) VALUES (%s,%s,'',%s,%s,%s,%s)",
                (_hash(secrets.token_urlsafe(32)), uid, int(time.time()) + 600,
                 _hash(confirmation), _encrypt(uid, creds.to_json()), profile["email"]))
    return (f"Google account: {profile['email']}\nNothing is connected yet.\n"
            f"Return to your own YoBot Telegram chat and send:\n/confirmgoogle {confirmation}\n"
            "Only confirm if this is the Google account you intended to connect. This code expires in 10 minutes.")


def confirm_connection(code):
    uid = config.get_current_user_id()
    if not config.is_authorized(uid):
        raise PermissionError("User is not approved")
    with _db() as execute:
        row = execute("DELETE FROM google_oauth_pending WHERE uid = %s AND confirmation_hash = %s AND expires > %s RETURNING token,email",
                      (uid, _hash(code), int(time.time()))).fetchone()
        if not row:
            return "That confirmation code is invalid or expired. Use /connectgoogle to start again."
        _decrypt(uid, row[0])
        execute("INSERT INTO google_accounts (uid,token,email,disabled) VALUES (%s,%s,%s,0) ON CONFLICT(uid) DO UPDATE SET token=excluded.token,email=excluded.email,disabled=0,sheet_id=''",
                (uid, row[0], row[1]))
    return f"Connected your Google account: {row[1]}. Gmail, Calendar and Sheets now use your account only."


def _record(uid):
    # Missing infrastructure never permits a guest to fall back to admin OAuth.
    if not (os.getenv("GOOGLE_ACCOUNTS_DATABASE_URL") or os.getenv("GOOGLE_ACCOUNTS_SQLITE")):
        return None
    with _db() as execute:
        return execute("SELECT token,email,sheet_id,disabled FROM google_accounts WHERE uid = %s", (uid,)).fetchone()


def credentials():
    uid = config.get_current_user_id()
    if not config.is_authorized(uid):
        raise NotConnected("This Telegram user is not approved")
    from google.oauth2.credentials import Credentials
    with _lock:
        row = _record(uid)
        if row:
            if row[3]:
                raise NotConnected("Google is disconnected. Use /connectgoogle.")
            creds = Credentials.from_authorized_user_info(json.loads(_decrypt(uid, row[0])))
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                request = Request()
                creds.refresh(lambda *a, **kw: request(*a, **dict(kw, timeout=20)))
                with _db() as execute:
                    execute("UPDATE google_accounts SET token = %s WHERE uid = %s AND disabled = 0", (_encrypt(uid, creds.to_json()), uid))
            return creds
        if config.is_admin(uid):
            path = Path(__file__).with_name("token.json")
            if path.exists():
                return Credentials.from_authorized_user_file(str(path))
        raise NotConnected("Connect your own Google account with /connectgoogle.")


def require_connection(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        uid = config.get_current_user_id()
        if not config.is_authorized(uid):
            raise NotConnected("This user is not approved")
        if not config.is_admin(uid):
            row = _record(uid)
            if not row or row[3]:
                raise NotConnected("Connect your own Google account with /connectgoogle.")
        return fn(*args, **kwargs)
    return wrapped


def connected():
    try:
        row = _record(config.get_current_user_id())
        return bool(row and not row[3])
    except Exception:
        return False


def error_message():
    return "Google access is unavailable. Use /connectgoogle to connect or renew your own account."


def disconnect():
    uid = config.get_current_user_id()
    with _db() as execute:
        row = execute("SELECT token FROM google_accounts WHERE uid = %s", (uid,)).fetchone()
        execute("DELETE FROM google_oauth_pending WHERE uid = %s", (uid,))
        execute("INSERT INTO google_accounts (uid,token,email,disabled) VALUES (%s,'','',1) ON CONFLICT(uid) DO UPDATE SET token='',email='',sheet_id='',disabled=1", (uid,))
    import gmail_service
    with gmail_service._draft_lock:
        gmail_service._drafts.pop(uid, None)
    revoked = False
    if row and row[0]:
        try:
            import requests
            token = json.loads(_decrypt(uid, row[0])).get("refresh_token")
            if token:
                revoked = requests.post("https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=20).status_code == 200
        except Exception:
            pass
    return "Google disconnected from YoBot. " + ("Google authorization was also revoked." if revoked else "You can also remove YoBot access in your Google Account security settings.")


def sheet_id(value=None):
    uid = config.get_current_user_id()
    with _db() as execute:
        row = execute("SELECT sheet_id FROM google_accounts WHERE uid = %s AND disabled = 0", (uid,)).fetchone()
        if row is None:
            raise NotConnected("Connect Google first with /connectgoogle.")
        if value is not None:
            execute("UPDATE google_accounts SET sheet_id = %s WHERE uid = %s AND disabled = 0", (value, uid))
            return value
        return row[0]
