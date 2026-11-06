import config
import os
import sqlite3
import json
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("SheetsSync")

BASE_DIR = os.path.dirname(__file__)
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
CONFIG_FILE = os.path.join(config.DATA_DIR, "sheets_config.json")

# Debounce lock and timer for background non-blocking synchronization
_sync_lock = threading.Lock()
_sync_timer: Optional[threading.Timer] = None
_is_syncing = False

SHEET_TABS = {
    "Expenses": {
        "headers": ["ID", "Date", "Category", "Amount (₹)", "Description", "User ID", "Logged At"],
        "db": os.path.join(config.DATA_DIR, "expenses.db"),
        "query": "SELECT id, expense_date, category, amount, description, user_id, created_at FROM expenses WHERE user_id = ? ORDER BY id ASC"
    },
    "Tasks": {
        "headers": ["ID", "Title", "Due Date", "Status", "Created At"],
        "db": os.path.join(config.DATA_DIR, "tasks.db"),
        "query": "SELECT id, title, due_date, completed, created_at FROM tasks WHERE user_id = ? ORDER BY id ASC"
    },
    "Habits": {
        "headers": ["ID", "Habit Name", "Total Days Logged", "Created At"],
        "db": os.path.join(config.DATA_DIR, "habits.db"),
        "query": "SELECT id, name, created_at FROM habits WHERE user_id = ? ORDER BY id ASC"
    },
    "Books": {
        "headers": ["ID", "Title", "Author", "Status", "Current Page", "Total Pages", "Rating", "Notes", "Updated At"],
        "db": os.path.join(config.DATA_DIR, "books.db"),
        "query": "SELECT id, title, author, status, current_page, total_pages, rating, notes, updated_at FROM books WHERE user_id = ? ORDER BY id ASC"
    },
    "Notes": {
        "headers": ["ID", "Title", "Content", "Tags", "Created At"],
        "db": os.path.join(config.DATA_DIR, "notes.db"),
        "query": "SELECT id, title, content, tags, created_at FROM notes WHERE user_id = ? ORDER BY id ASC"
    }
}

def load_sheet_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_sheet_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save sheets_config.json: {e}")

@config.require_admin
def get_spreadsheet_id() -> Optional[str]:
    # Check environment variable first
    env_id = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()
    if env_id:
        return env_id
    cfg = load_sheet_config()
    return cfg.get("spreadsheet_id")

@config.require_admin
def get_spreadsheet_url() -> Optional[str]:
    sid = get_spreadsheet_id()
    if sid:
        return f"https://docs.google.com/spreadsheets/d/{sid}/edit"
    return None

@config.require_admin
def get_credentials():
    """
    Retrieves and refreshes authorized Google OAuth credentials from token.json.
    """
    if not os.path.exists(TOKEN_FILE):
        return None, "token_missing"

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(TOKEN_FILE)
        if creds and creds.expired and creds.refresh_token:
            try:
                request = Request()
                creds.refresh(lambda *a, **kw: request(*a, **dict(kw, timeout=20)))
                with open(TOKEN_FILE, "w", encoding="utf-8") as token_out:
                    token_out.write(creds.to_json())
            except Exception as ref_err:
                logger.warning("Google Sheets authorization refresh failed (%s)", type(ref_err).__name__)
                return None, "auth_expired"

        # Check if sheets scope is present
        scopes = getattr(creds, "scopes", []) or []
        has_sheets = any("spreadsheets" in s for s in scopes)
        if not has_sheets:
            return creds, "insufficient_scope"

        return creds, "ok"
    except Exception as e:
        logger.error(f"Error loading Google credentials: {e}")
        return None, str(e)

def get_sheets_service():
    creds, status = get_credentials()
    if not creds:
        return None, status
    if status != "ok":
        return None, status
    try:
        from googleapiclient.discovery import build
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        service = build("sheets", "v4", http=AuthorizedHttp(creds, http=httplib2.Http(timeout=20)), cache_discovery=False)
        return service, "ok"
    except Exception as e:
        logger.error(f"Failed to build Sheets service: {e}")
        return None, str(e)

def ensure_spreadsheet(service) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns existing spreadsheet ID or creates a fully structured new one.
    """
    sid = get_spreadsheet_id()
    if sid:
        try:
            # Verify existence
            service.spreadsheets().get(spreadsheetId=sid).execute()
            return sid, None
        except Exception as exc:
            return None, f"Configured spreadsheet is inaccessible: {exc}"

    # Create new Spreadsheet
    try:
        spreadsheet_body = {
            "properties": {
                "title": "YoBot — Second Brain (Executive Database)"
            },
            "sheets": [
                {"properties": {"title": "Expenses"}},
                {"properties": {"title": "Tasks"}},
                {"properties": {"title": "Habits"}},
                {"properties": {"title": "Books"}},
                {"properties": {"title": "Notes"}}
            ]
        }
        res = service.spreadsheets().create(body=spreadsheet_body).execute()
        new_sid = res["spreadsheetId"]
        
        cfg = load_sheet_config()
        cfg["spreadsheet_id"] = new_sid
        cfg["created_at"] = datetime.now().isoformat()
        save_sheet_config(cfg)
        logger.info(f"Created new YoBot Google Spreadsheet: {new_sid}")

        # Write header rows
        header_updates = []
        for tab_name, meta in SHEET_TABS.items():
            header_updates.append({
                "range": f"'{tab_name}'!A1:Z1",
                "values": [meta["headers"]]
            })

        service.spreadsheets().values().batchUpdate(
            spreadsheetId=new_sid,
            body={
                "valueInputOption": "RAW",
                "data": header_updates
            }
        ).execute()

        return new_sid, None
    except Exception as e:
        logger.error(f"Failed to create Google Spreadsheet: {e}")
        return None, str(e)

@config.require_admin
def extract_table_data(tab_name: str) -> list:
    """
    Pulls data rows from the corresponding SQLite database for Google Sheets.
    """
    meta = SHEET_TABS.get(tab_name)
    if not meta or not os.path.exists(meta["db"]):
        raise FileNotFoundError(f"Source database missing for {tab_name}")

    rows = []
    conn = None
    try:
        conn = sqlite3.connect(meta["db"])
        cursor = conn.cursor()

        if tab_name == "Expenses":
            cursor.execute(meta["query"], (config.ADMIN_USER_ID,))
            for r in cursor.fetchall():
                # [id, expense_date, category, amount, description, user_id, created_at]
                rows.append([
                    r[0],
                    str(r[1] or ""),
                    str(r[2] or ""),
                    float(r[3] or 0),
                    str(r[4] or ""),
                    str(r[5] or ""),
                    str(r[6] or "")
                ])
        elif tab_name == "Tasks":
            cursor.execute(meta["query"], (config.ADMIN_USER_ID,))
            for r in cursor.fetchall():
                # [id, title, due_date, completed, created_at]
                rows.append([
                    r[0],
                    str(r[1] or ""),
                    str(r[2] or "-"),
                    "✅ Completed" if r[3] else "⏳ Pending",
                    str(r[4] or "")
                ])
        elif tab_name == "Habits":
            cursor.execute(meta["query"], (config.ADMIN_USER_ID,))
            habits = cursor.fetchall()
            for h in habits:
                h_id, name, created_at = h[0], h[1], h[2]
                try:
                    count_cursor = conn.cursor()
                    count_cursor.execute("SELECT count(*) FROM habit_logs WHERE habit_id = ?", (h_id,))
                    count = count_cursor.fetchone()[0]
                except Exception:
                    count = 0
                rows.append([h_id, str(name or ""), count, str(created_at or "")])
        elif tab_name == "Books":
            cursor.execute(meta["query"], (config.ADMIN_USER_ID,))
            for r in cursor.fetchall():
                # [id, title, author, status, current_page, total_pages, rating, notes, updated_at]
                rows.append([
                    r[0],
                    str(r[1] or ""),
                    str(r[2] or "Unknown"),
                    str(r[3] or "Reading"),
                    int(r[4] or 0),
                    int(r[5] or 0),
                    float(r[6] or 0),
                    str(r[7] or ""),
                    str(r[8] or "")
                ])
        elif tab_name == "Notes":
            cursor.execute(meta["query"], (config.ADMIN_USER_ID,))
            for r in cursor.fetchall():
                # [id, title, content, tags, created_at]
                rows.append([
                    r[0],
                    str(r[1] or ""),
                    str(r[2] or ""),
                    str(r[3] or "-"),
                    str(r[4] or "")
                ])
    except Exception as e:
        logger.error(f"Error extracting data for {tab_name}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

    return rows

@config.require_admin
def sync_all_to_sheets() -> Dict[str, Any]:
    """
    Executes a complete synchronization of all SQLite tables to Google Sheets in batch.
    """
    if config.SHEETS_DURABLE_STORAGE:
        import sheets_store
        return sheets_store.sync_now()
    global _is_syncing
    with _sync_lock:
        if _is_syncing:
            return {"status": "in_progress", "message": "Sync already active."}
        _is_syncing = True

    try:
        service, status = get_sheets_service()
        if not service:
            if status == "token_missing":
                return {"status": "unlinked", "message": "Google account not linked. Run python setup_google.py to link."}
            elif status == "insufficient_scope":
                return {
                    "status": "need_auth",
                    "message": "Google Sheets permissions needed! Please run 'python setup_google.py' once to approve Sheets access."
                }
            return {"status": "error", "message": f"Auth error: {status}"}

        sid, err = ensure_spreadsheet(service)
        if not sid:
            return {"status": "error", "message": f"Could not create/find spreadsheet: {err}"}

        # Clear existing data rows (keep headers) and update in batch
        batch_data = []
        counts = {}

        for tab_name, meta in SHEET_TABS.items():
            data_rows = extract_table_data(tab_name)
            counts[tab_name] = len(data_rows)
            if data_rows:
                batch_data.append({
                    "range": f"'{tab_name}'!A2",
                    "values": data_rows
                })

        if batch_data:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=sid,
                body={
                    "valueInputOption": "RAW",
                    "data": batch_data
                }
            ).execute()

        # Remove stale trailing rows only after all source reads and replacement writes succeed.
        for tab_name, count in counts.items():
            service.spreadsheets().values().clear(
                spreadsheetId=sid,
                range=f"'{tab_name}'!A{count + 2}:Z"
            ).execute()

        # Update last synced record
        now_iso = datetime.now().isoformat()
        cfg = load_sheet_config()
        cfg["spreadsheet_id"] = sid
        cfg["last_sync"] = now_iso
        cfg["counts"] = counts
        save_sheet_config(cfg)

        url = f"https://docs.google.com/spreadsheets/d/{sid}/edit"
        logger.info(f"Google Sheets sync successful: {counts}")
        return {
            "status": "success",
            "spreadsheet_id": sid,
            "url": url,
            "counts": counts,
            "timestamp": now_iso
        }
    except Exception as e:
        logger.error(f"Sync to Google Sheets encountered error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        with _sync_lock:
            _is_syncing = False

def _run_background_sync():
    try:
        with config.user_context(config.ADMIN_USER_ID, "Revanth Sir"):
            sync_all_to_sheets()
    except Exception as e:
        logger.warning(f"Background sync notice: {e}")

def trigger_background_sync(delay_seconds: float = 3.0):
    """
    Non-blocking debounced sync. Defers execution by delay_seconds.
    If called again within delay_seconds, resets the timer so rapid operations
    (e.g. logging 3 expenses in 5s) only trigger 1 Google API call.
    """
    if config.SHEETS_DURABLE_STORAGE:
        return  # Durable writes happen synchronously; periodic job retries failures.
    global _sync_timer
    with _sync_lock:
        if _sync_timer is not None:
            _sync_timer.cancel()
        _sync_timer = threading.Timer(delay_seconds, _run_background_sync)
        _sync_timer.daemon = True
        _sync_timer.start()

@config.require_admin
def get_sync_status() -> dict:
    """
    Returns quick status summary of Google Sheets sync.
    """
    creds, status = get_credentials()
    sid = get_spreadsheet_id()
    cfg = load_sheet_config()
    
    import sheets_store
    return {
        "linked": creds is not None and status == "ok",
        "status_code": status,
        "spreadsheet_id": sid,
        "url": f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else None,
        "last_sync": cfg.get("last_sync"),
        "counts": cfg.get("counts", {}),
        "durable": sheets_store.health_status(),
    }

@config.require_admin
def get_sheets_link() -> str:
    """
    Returns the live Google Sheets URL for viewing expenses, tasks, habits, books, and notes.
    """
    url = get_spreadsheet_url()
    if url:
        _, auth_status = get_credentials()
        if auth_status != "ok":
            return f"Your saved Google workbook: {url}\nGoogle sync is disconnected. Reconnect Google before new records can be saved there."
        return f"Your Google Sheets workbook: {url}"
    status = get_sync_status()
    if status.get("status_code") == "insufficient_scope":
        return "Google Sheets is pending one-time authorization. Run 'python setup_google.py' in your terminal to approve Google Sheets access."
    return "Google Sheets is not linked yet. Please run 'python setup_google.py' to link your Google account."

@config.require_admin
def sync_google_sheets() -> str:
    """
    Manually triggers an immediate full synchronization of all SQLite tables to Google Sheets.
    """
    res = sync_all_to_sheets()
    if res.get("status") == "success":
        return f"Successfully synchronized all records to Google Sheets: {res.get('url')}"
    return f"Sync notice: {res.get('message', 'Unable to sync at this time.')}"

