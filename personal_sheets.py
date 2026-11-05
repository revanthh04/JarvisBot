"""User-owned Sheets exports, separate from the owner's durable storage workbook."""
from contextlib import closing
import sqlite3
import threading
import config
import backup_service
import google_accounts

_lock = threading.RLock()


@google_accounts.require_connection
def get_personal_sheets_link() -> str:
    """Return only the active user's connected Google workbook."""
    sid = google_accounts.sheet_id()
    return f"Your Google Sheet: https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else "Use /syncsheets to create your own Google workbook and export your records."


@google_accounts.require_connection
def sync_personal_sheets() -> str:
    """Export only the current user's records to their Google account."""
    from googleapiclient.discovery import build
    uid = config.get_current_user_id()
    with _lock:
        try:
            service = build("sheets", "v4", credentials=google_accounts.credentials(), cache_discovery=False)
            sid = google_accounts.sheet_id()
            if not sid:
                created = service.spreadsheets().create(body={"properties": {"title": "YoBot — My Records"},
                    "sheets": [{"properties": {"title": name}} for name in backup_service.DATABASES]}).execute()
                sid = created["spreadsheetId"]
                google_accounts.sheet_id(sid)
            meta = service.spreadsheets().get(spreadsheetId=sid, fields="sheets(properties)").execute()
            props = {s["properties"]["title"]: s["properties"] for s in meta["sheets"]}
            requests = []
            for name, info in backup_service.DATABASES.items():
                if name not in props:
                    return "A workbook tab is missing. Restore its original name before syncing; no records were changed."
                with closing(sqlite3.connect(info["file"])) as conn:
                    if name == "habit_logs":
                        rows = conn.execute("SELECT l.* FROM habit_logs l JOIN habits h ON l.habit_id=h.id WHERE h.user_id=? ORDER BY l.id", (uid,)).fetchall()
                    else:
                        rows = conn.execute(f"SELECT {','.join(info['columns'])} FROM {name} WHERE user_id=? ORDER BY id", (uid,)).fetchall()
                data = [info["columns"], *rows]
                p = props[name]
                for dimension, size, count in (("ROWS", len(data), p["gridProperties"]["rowCount"]), ("COLUMNS", len(info["columns"]), p["gridProperties"]["columnCount"])):
                    if size > count:
                        requests.append({"appendDimension": {"sheetId": p["sheetId"], "dimension": dimension, "length": size-count}})
                def cell(v):
                    return {} if v is None else {"userEnteredValue": {"numberValue": v} if isinstance(v, (int, float)) else {"stringValue": str(v)}}
                requests.append({"updateCells": {"range": {"sheetId": p["sheetId"]},
                    "rows": [{"values": [cell(v) for v in row]} for row in data], "fields": "userEnteredValue"}})
            service.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": requests}).execute()
            return f"Your records were exported to your Google Sheet: https://docs.google.com/spreadsheets/d/{sid}/edit"
        except Exception:
            return "Your Google Sheets export couldn't be completed. Check /googlestatus; use /connectgoogle if sign-in has expired."
