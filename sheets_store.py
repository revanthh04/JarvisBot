"""Durable, versioned admin snapshots in the bot's existing Google workbook.

SQLite is a cache. Restore must succeed before the bot may write. The seven
hidden recovery tabs contain JSON-typed cells; the visible tabs are dashboards.
All tables, deletions, dashboards and revision metadata change in one atomic
Sheets batch. A named range is consumed/replaced in that batch to fence stale
writers. Manual edits to recovery tabs fail the checksum instead of being lost.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import logging
import sqlite3
import threading
import uuid

import config
import backup_service
import sheets_service

log = logging.getLogger("SheetsStore")
SCHEMA = 1
TABS = {name: "_store_" + name for name in backup_service.DATABASES}
META_TAB = "_store_state"
FENCE_NAME = "YOBOT_STORAGE_REVISION"
_lock = threading.RLock()
_ready = False
_pending = False
_revision = None
_digest = None
_attempt = None
_last_sync = None


def enabled():
    return config.SHEETS_DURABLE_STORAGE


def mark_pending():
    global _pending
    _pending = True

_issue = ""

class StorageAccessError(RuntimeError):
    pass

def recovery_advice():
    return _issue or "I will retry the save. Keep the bot running while changes are pending."


def health_status():
    return {"enabled": enabled(), "ready": _ready, "pending": _pending, "last_sync": _last_sync}


def warning_text(user_id=None):
    user_id = config.get_current_user_id() if user_id is None else user_id
    if enabled() and user_id == config.ADMIN_USER_ID and (_pending or not _ready):
        return ("⚠️ Google Sheets save is pending. Recent changes are only on this server "
                "and could be lost if it restarts. " + recovery_advice())
    return ""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(tables):
    return hashlib.sha256(canonical(tables).encode("utf-8")).hexdigest()


def admin_tables(vault):
    source = vault["tables"]
    result = {}
    for name, meta in backup_service.DATABASES.items():
        if name == "habit_logs":
            continue
        result[name] = [{col: row[col] for col in meta["columns"]}
                        for row in source[name] if row["user_id"] == config.ADMIN_USER_ID]
    habit_ids = {row["id"] for row in result["habits"]}
    result["habit_logs"] = [{col: row[col] for col in backup_service.DATABASES["habit_logs"]["columns"]}
                            for row in source["habit_logs"] if row["habit_id"] in habit_ids]
    for rows in result.values():
        rows.sort(key=lambda r: r["id"])
    validate_tables(result)
    return result


def validate_tables(tables):
    if set(tables) != set(TABS):
        raise ValueError("Incomplete recovery tables")
    for name, meta in backup_service.DATABASES.items():
        rows = tables[name]
        if not isinstance(rows, list):
            raise ValueError("Invalid recovery rows")
        ids = set()
        for row in rows:
            if set(row) != set(meta["columns"]) or type(row["id"]) is not int or row["id"] <= 0:
                raise ValueError("Invalid recovery record")
            if row["id"] in ids:
                raise ValueError("Duplicate recovery ID")
            ids.add(row["id"])
            if name != "habit_logs" and row["user_id"] != config.ADMIN_USER_ID:
                raise ValueError("Recovery owner mismatch")
            if any(not isinstance(value, (str, int, float, type(None))) for value in row.values()):
                raise ValueError("Invalid recovery value")
    habits = {r["id"] for r in tables["habits"]}
    if any(r["habit_id"] not in habits for r in tables["habit_logs"]):
        raise ValueError("Orphan habit log")
    canonical(tables)  # Reject NaN/infinities before any write.


def connect():
    # Internal persistence may run after a guest mutation; identity never changes
    # which data is exported. Only admin_tables() reaches this workbook.
    with config.user_context(config.ADMIN_USER_ID, "Revanth Sir"):
        service, status = sheets_service.get_sheets_service()
        sid = sheets_service.get_spreadsheet_id()
    if service is None or not sid:
        raise StorageAccessError(status if service is None else "missing_workbook")
    return service, sid


def metadata(service, sid):
    return service.spreadsheets().get(spreadsheetId=sid,
        fields="sheets(properties),namedRanges(namedRangeId,name)").execute()


def read_remote(service, sid, meta=None):
    meta = metadata(service, sid) if meta is None else meta
    props = {s["properties"]["title"]: s["properties"] for s in meta["sheets"]}
    if not set([*TABS.values(), META_TAB]).issubset(props):
        raise ValueError("Recovery store is missing; run explicit bootstrap once")
    names = [META_TAB, *TABS.values()]
    # Read all payloads + their checksum in ONE API request, not separate reads.
    ranges = [f"'{name}'!A1:{'B' if name == META_TAB else 'Z'}{props[name]['gridProperties']['rowCount']}"
              for name in names]
    values = service.spreadsheets().values().batchGet(spreadsheetId=sid,
        ranges=ranges, valueRenderOption="UNFORMATTED_VALUE").execute()["valueRanges"]
    if len(values) != len(names):
        raise ValueError("Incomplete remote read")
    state_rows = values[0].get("values", [])
    if not state_rows or state_rows[0] != ["state", "json"] or len(state_rows) != 2:
        raise ValueError("Invalid recovery state")
    state = json.loads(state_rows[1][1])
    if state["schema"] != SCHEMA or state["owner"] != config.ADMIN_USER_ID:
        raise ValueError("Unsupported recovery schema or owner")
    if not any(n["namedRangeId"] == state["revision"] and n["name"] == FENCE_NAME
               for n in meta.get("namedRanges", [])):
        raise ValueError("Recovery revision changed during read")
    tables = {}
    for (name, spec), data in zip(backup_service.DATABASES.items(), values[1:]):
        rows = data.get("values", [])
        if not rows or rows[0] != spec["columns"]:
            raise ValueError("Recovery headers changed")
        if any(len(row) != len(spec["columns"]) for row in rows[1:]):
            raise ValueError("Incomplete recovery row")
        tables[name] = [dict(zip(spec["columns"], [json.loads(v) for v in row])) for row in rows[1:]]
    validate_tables(tables)
    if digest(tables) != state["digest"] or {k: len(v) for k, v in tables.items()} != state["counts"]:
        raise ValueError("Recovery checksum mismatch")
    return state, tables


def visible_tables(tables):
    """Human-readable views; strings are always literal, never formulas."""
    t = tables
    result = {
        "Expenses": [sheets_service.SHEET_TABS["Expenses"]["headers"]] + [
            [r[k] for k in ("id", "expense_date", "category", "amount", "description", "user_id", "created_at")] for r in t["expenses"]],
        "Tasks": [sheets_service.SHEET_TABS["Tasks"]["headers"]] + [
            [r["id"], r["title"], r["due_date"], "Completed" if r["completed"] else "Pending", r["created_at"]] for r in t["tasks"]],
        "Habits": [sheets_service.SHEET_TABS["Habits"]["headers"]] + [
            [r["id"], r["name"], sum(l["habit_id"] == r["id"] for l in t["habit_logs"]), r["created_at"]] for r in t["habits"]],
        "Books": [sheets_service.SHEET_TABS["Books"]["headers"]] + [
            [r[k] for k in ("id", "title", "author", "status", "current_page", "total_pages", "rating", "notes", "updated_at")] for r in t["books"]],
        "Notes": [sheets_service.SHEET_TABS["Notes"]["headers"]] + [
            [r[k] for k in ("id", "title", "content", "tags", "created_at")] for r in t["notes"]],
        "Reminders": [["ID", "Message", "Due At", "Finished", "Repeat Minutes", "Last Delivered"]] + [
            [r[k] for k in ("id", "message", "remind_at", "triggered", "repeat_interval_minutes", "last_triggered_at")] for r in t["reminders"]],
        "Habit History": [["ID", "Habit ID", "Date"]] + [[r[k] for k in ("id", "habit_id", "log_date")] for r in t["habit_logs"]],
    }
    return result


def batch_for_snapshot(tables, meta, previous=None, revision=None):
    validate_tables(tables)
    state = {"schema": SCHEMA, "owner": config.ADMIN_USER_ID,
             "revision": revision or uuid.uuid4().hex, "digest": digest(tables),
             "counts": {k: len(v) for k, v in tables.items()},
             "updated_at": datetime.now(timezone.utc).isoformat()}
    grids = visible_tables(tables)
    for name, title in TABS.items():
        cols = backup_service.DATABASES[name]["columns"]
        grids[title] = [cols] + [[canonical(row[col]) for col in cols] for row in tables[name]]
    grids[META_TAB] = [["state", "json"], ["current", canonical(state)]]
    props = {s["properties"]["title"]: s["properties"] for s in meta["sheets"]}
    requests = []
    if previous:
        # Missing-range deletion is idempotent in Sheets, so it cannot fence
        # writers. Retain a unique consumed-revision marker: adding the same
        # ID twice rejects the entire atomic batch.
        requests.append({"addNamedRange": {"namedRange": {
            "namedRangeId": "consumed_" + previous,
            "name": "YOBOT_CONSUMED_" + previous,
            "range": {"sheetId": props[META_TAB]["sheetId"],
                      "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 1}}}})
        requests.append({"deleteNamedRange": {"namedRangeId": previous}})
    used_ids = {p["sheetId"] for p in props.values()}
    for title, rows in grids.items():
        created = title not in props
        if created:
            sheet_id = max(used_ids | {0}) + 1
            used_ids.add(sheet_id)
            props[title] = {"sheetId": sheet_id, "title": title,
                "hidden": title.startswith("_store_"),
                "gridProperties": {"rowCount": max(100, len(rows)), "columnCount": max(12, len(rows[0])), "frozenRowCount": 1}}
            requests.append({"addSheet": {"properties": props[title]}})
        p = props[title]
        sheet_id = p["sheetId"]
        if len(rows) > p["gridProperties"]["rowCount"]:
            requests.append({"appendDimension": {"sheetId": sheet_id, "dimension": "ROWS",
                "length": len(rows) - p["gridProperties"]["rowCount"]}})
        if len(rows[0]) > p["gridProperties"]["columnCount"]:
            requests.append({"appendDimension": {"sheetId": sheet_id, "dimension": "COLUMNS",
                "length": len(rows[0]) - p["gridProperties"]["columnCount"]}})
        def cell(value):
            if value is None:
                return {}
            if isinstance(value, (int, float)):
                return {"userEnteredValue": {"numberValue": value}}
            return {"userEnteredValue": {"stringValue": str(value)}}
        requests.append({"updateCells": {"range": {"sheetId": sheet_id},
            "rows": [{"values": [cell(v) for v in row]} for row in rows], "fields": "userEnteredValue"}})
        if created:
            requests.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"backgroundColor": {"red": .12, "green": .22, "blue": .36},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
                "fields": "userEnteredFormat"}})
            requests.append({"addProtectedRange": {"protectedRange": {"range": {"sheetId": sheet_id},
                "description": "Managed by YoBot. Make changes through Telegram to keep recovery consistent.", "warningOnly": True}}})
    requests.append({"addNamedRange": {"namedRange": {"namedRangeId": state["revision"], "name": FENCE_NAME,
        "range": {"sheetId": props[META_TAB]["sheetId"], "startRowIndex": 1, "endRowIndex": 2,
                  "startColumnIndex": 1, "endColumnIndex": 2}}}})
    return {"requests": requests}, state


def replace_local(tables):
    """Replace admin cache INCLUDING empty tables; guest records stay local."""
    validate_tables(tables)
    paths = list(dict.fromkeys(i["file"] for i in backup_service.DATABASES.values()))
    with closing(sqlite3.connect(paths[0])) as conn:
        aliases = {paths[0]: "main"}
        for index, path in enumerate(paths[1:]):
            alias = f"cache{index}"
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (path,))
            aliases[path] = alias
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            def table(name):
                info = backup_service.DATABASES[name]
                return f'{aliases[info["file"]]}.{name}'
            conn.execute(f"DELETE FROM {table('habit_logs')} WHERE habit_id IN "
                         f"(SELECT id FROM {table('habits')} WHERE user_id = ?)", (config.ADMIN_USER_ID,))
            for name in TABS:
                if name != "habit_logs":
                    conn.execute(f"DELETE FROM {table(name)} WHERE user_id = ?", (config.ADMIN_USER_ID,))
            for name, info in backup_service.DATABASES.items():
                cols = info["columns"]
                conn.executemany(f"INSERT INTO {table(name)} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                                 [[r[c] for c in cols] for r in tables[name]])


def _accepted(state):
    global _revision, _digest, _last_sync, _pending, _attempt, _issue
    _issue = ""
    _revision, _digest, _last_sync = state["revision"], state["digest"], state["updated_at"]
    _pending, _attempt = False, None
    with config.user_context(config.ADMIN_USER_ID):
        cfg = sheets_service.load_sheet_config()
        cfg.update(last_sync=_last_sync, counts=state["counts"])
        sheets_service.save_sheet_config(cfg)


def restore_on_startup():
    global _ready
    # Same lock ordering as backup: never acquire vault lock while holding _lock.
    with backup_service._vault_lock, _lock:
        _ready = False
        service, sid = connect()
        state, tables = read_remote(service, sid)
        replace_local(tables)
        _accepted(state)
        config.MISSING_DATABASES.clear()
        _ready = True
        log.info("Google Sheets recovery complete: %s", state["counts"])
        return {"status": "restored", "counts": state["counts"]}


def persist(vault):
    global _attempt, _pending, _issue
    with _lock:
        try:
            if not _ready:
                raise RuntimeError("Restore must succeed before writing")
            tables = admin_tables(vault)
            target_digest = digest(tables)
            service, sid = connect()
            meta = metadata(service, sid)
            state, remote = read_remote(service, sid, meta)
            # If a request succeeded but the response was lost, recognize it.
            if _attempt and (state["revision"], state["digest"]) == _attempt:
                _accepted(state)
            if state["revision"] != _revision or state["digest"] != _digest:
                if target_digest == state["digest"]:
                    _accepted(state)
                else:
                    raise ValueError("Cloud and local records differ")
            if target_digest != _digest:
                body, proposed = batch_for_snapshot(tables, meta, previous=_revision)
                _attempt = (proposed["revision"], proposed["digest"])
                service.spreadsheets().batchUpdate(spreadsheetId=sid, body=body).execute()
                state, verified = read_remote(service, sid)
                if (state["revision"], state["digest"]) != _attempt:
                    raise RuntimeError("Cloud save could not be verified")
            _accepted(state)
            return {"status": "success", "counts": state["counts"], "timestamp": _last_sync,
                    "url": f"https://docs.google.com/spreadsheets/d/{sid}/edit"}
        except Exception as exc:
            _pending = True
            if isinstance(exc, StorageAccessError) and str(exc) in ("auth_expired", "token_missing", "insufficient_scope"):
                _issue = "Google authorization needs attention. Renew the owner's Google authorization and update GOOGLE_TOKEN_JSON in Render. Use /repair to verify."
            elif isinstance(exc, ValueError):
                _issue = "The records failed a consistency check. Preserve the local copy and review the workbook before restarting. I will leave both copies intact."
            else:
                _issue = "I will retry automatically. Use /repair for an immediate check."
            # API exceptions can include user values; log only the class.
            log.warning("Cloud save pending (%s); remote data preserved", type(exc).__name__)
            return {"status": "pending", "message": "Google Sheets save is pending; local data retained for retry."}


def sync_now():
    with backup_service._vault_lock:
        try:
            return persist(backup_service.read_snapshot())
        except Exception:
            mark_pending()
            return {"status": "pending", "message": "Could not read local data; cloud data preserved."}
