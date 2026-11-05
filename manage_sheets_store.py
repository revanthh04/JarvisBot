"""Explicit migration and read-only verification for the bot's Sheets store.

--bootstrap preserves the existing live dashboard as the source for its five
tables, supplements fields it never exported from the saved SQLite data, and
creates the complete recovery store. Never overwrites an initialized store.
No Telegram polling or messages. Prints only counts/status, never row contents.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

import config
import backup_service
import sheets_service
import sheets_store as store


def legacy_snapshot(service, sid, meta):
    snapshot = backup_service.read_snapshot()
    tables = store.admin_tables(snapshot)
    props = {s["properties"]["title"]: s["properties"] for s in meta["sheets"]}
    names = list(sheets_service.SHEET_TABS)
    if not set(names).issubset(props):
        raise ValueError("Legacy dashboard is incomplete; migration needs review")
    ranges = [f"'{name}'!A1:Z{props[name]['gridProperties']['rowCount']}" for name in names]
    data = service.spreadsheets().values().batchGet(spreadsheetId=sid, ranges=ranges,
                valueRenderOption="UNFORMATTED_VALUE").execute()["valueRanges"]
    timestamp = datetime.now(timezone.utc).isoformat()
    maps = {
        "Expenses": ("expenses", ["id", "expense_date", "category", "amount", "description", "user_id", "created_at"]),
        "Tasks": ("tasks", ["id", "title", "due_date", "completed", "created_at"]),
        "Habits": ("habits", ["id", "name", None, "created_at"]),
        "Books": ("books", ["id", "title", "author", "status", "current_page", "total_pages", "rating", "notes", "updated_at"]),
        "Notes": ("notes", ["id", "title", "content", "tags", "created_at"]),
    }
    history_gaps = 0
    for title, value_range in zip(names, data):
        rows = value_range.get("values", [])
        if not rows or rows[0] != sheets_service.SHEET_TABS[title]["headers"]:
            raise ValueError("Legacy headers do not match; migration needs review")
        table, columns = maps[title]
        local = {r["id"]: r for r in tables[table]}
        migrated = []
        for raw in rows[1:]:
            if not raw or all(v == "" for v in raw):
                continue
            record_id = int(raw[0])
            row = dict(local.get(record_id, {c: None for c in backup_service.DATABASES[table]["columns"]}))
            row.update(id=record_id, user_id=config.ADMIN_USER_ID)
            for col, value in zip(columns, raw + [""] * (len(columns) - len(raw))):
                if col:
                    row[col] = value
            row["id"] = record_id
            row["user_id"] = int(row["user_id"])
            if table == "tasks":
                status = str(row["completed"]).lower()
                if "completed" not in status and "pending" not in status:
                    raise ValueError("Unrecognized task status")
                row["completed"] = int("completed" in status)
                if row["due_date"] in ("-", ""):
                    row["due_date"] = None
            elif table == "expenses":
                row["amount"] = float(row["amount"])
            elif table == "books":
                for col in ("current_page", "total_pages"):
                    row[col] = int(row[col] or 0)
                row["rating"] = float(row["rating"]) if row["rating"] not in (None, "") else None
                row["created_at"] = row["created_at"] or row["updated_at"] or timestamp
            elif table == "habits":
                known_logs = sum(r["habit_id"] == record_id for r in tables["habit_logs"])
                history_gaps += max(0, int(raw[2] or 0) - known_logs)
            migrated.append(row)
        tables[table] = sorted(migrated, key=lambda r: r["id"])
    habits = {r["id"] for r in tables["habits"]}
    tables["habit_logs"] = [r for r in tables["habit_logs"] if r["habit_id"] in habits]
    store.validate_tables(tables)
    # Ignored by git: preserve the before-migration source for manual recovery.
    path = Path(config.DATA_DIR) / f"storage-migration-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"local": snapshot, "legacy": data, "migrated": tables,
                               "missing_habit_dates": history_gaps}, ensure_ascii=False, indent=2), encoding="utf-8")
    return tables, history_gaps


def verify_recovery(tables):
    """Actually restore into separate temporary SQLite files and compare hashes."""
    with tempfile.TemporaryDirectory(prefix="yobot-recovery-") as tmp:
        test_databases = {name: dict(info, file=str(Path(tmp) / Path(info["file"]).name))
                          for name, info in backup_service.DATABASES.items()}
        for name in ("expenses", "books", "notes", "tasks", "habits", "reminders"):
            # Copy schema only, never modify production SQLite or import a service
            # (service imports perform migrations on their live DB_FILE).
            original = backup_service.DATABASES[name]["file"]
            with closing(sqlite3.connect(f"file:{Path(original).as_posix()}?mode=ro", uri=True)) as source:
                schemas = source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'").fetchall()
            with closing(sqlite3.connect(test_databases[name]["file"])) as target:
                for (sql,) in schemas:
                    target.execute(sql)
                target.commit()
        with patch.object(backup_service, "DATABASES", test_databases):
            store.replace_local(tables)
            restored = store.admin_tables(backup_service.read_snapshot())
        if store.digest(restored) != store.digest(tables):
            raise ValueError("SQLite restore did not match the cloud snapshot")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--verify-recovery", action="store_true")
    parser.add_argument("--probe-fence", action="store_true")
    args = parser.parse_args()
    service, sid = store.connect()
    meta = store.metadata(service, sid)
    if args.probe_fence:
        # Invalid range must reject the batch; no existing object is addressed.
        from googleapiclient.errors import HttpError
        try:
            service.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": [
                {"deleteNamedRange": {"namedRangeId": "yobot_nonexistent_probe_9a27c2d24d39410fa285ec3ac9499fbe"}}
            ]}).execute()
        except HttpError as exc:
            if exc.resp.status == 400 and "named range" in str(exc).lower():
                print(json.dumps({"fence_missing_revision_rejected": True}))
                return
            raise
        raise RuntimeError("Sheets accepted a missing fence; do not enable storage")
    titles = {s["properties"]["title"] for s in meta["sheets"]}
    if args.bootstrap:
        if store.META_TAB in titles or any(t in titles for t in store.TABS.values()):
            raise ValueError("Store already exists; bootstrap will not overwrite it")
        tables, history_gaps = legacy_snapshot(service, sid, meta)
        verify_recovery(tables)  # Validate DB constraints BEFORE changing cloud state.
        body, expected = store.batch_for_snapshot(tables, meta)
        service.spreadsheets().batchUpdate(spreadsheetId=sid, body=body).execute()
        state, verified = store.read_remote(service, sid)
        if state["revision"] != expected["revision"] or state["digest"] != expected["digest"]:
            raise ValueError("Bootstrap readback did not match")
        print(json.dumps({"bootstrapped": True, "counts": state["counts"], "missing_habit_dates": history_gaps}))
    else:
        if store.META_TAB in titles:
            state, tables = store.read_remote(service, sid)
            result = {"store_valid": True, "counts": state["counts"], "updated_at": state["updated_at"]}
            if args.verify_recovery:
                result["sqlite_recovery_verified"] = verify_recovery(tables)
            print(json.dumps(result))
        else:
            tables, gaps = legacy_snapshot(service, sid, meta)
            print(json.dumps({"ready_to_migrate": True, "counts": {k: len(v) for k, v in tables.items()},
                              "missing_habit_dates": gaps}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No credentials, row contents or full Google API errors in logs.
        print(json.dumps({"ok": False, "error_type": type(exc).__name__,
                          "action": "Storage was not verified; inspect configuration before deploying."}))
        raise SystemExit(1)
