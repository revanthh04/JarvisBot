import sqlite3
import json
import os
import logging
import tempfile
import threading
from contextlib import closing
from functools import wraps
import config
from datetime import datetime

logger = logging.getLogger("DataGuardian")

BASE_DIR = config.DATA_DIR
VAULT_FILE = os.path.join(BASE_DIR, "data_vault_backup.json")

DATABASES = {
    "expenses": {
        "file": os.path.join(BASE_DIR, "expenses.db"),
        "table": "expenses",
        "columns": ["id", "user_id", "amount", "category", "description", "expense_date", "created_at"]
    },
    "books": {
        "file": os.path.join(BASE_DIR, "books.db"),
        "table": "books",
        "columns": ["id", "user_id", "title", "author", "status", "current_page", "total_pages", "rating", "notes", "created_at", "updated_at"]
    },
    "notes": {
        "file": os.path.join(BASE_DIR, "notes.db"),
        "table": "notes",
        "columns": ["id", "user_id", "title", "content", "tags", "created_at"]
    },
    "tasks": {
        "file": os.path.join(BASE_DIR, "tasks.db"),
        "table": "tasks",
        "columns": ["id", "user_id", "title", "due_date", "completed", "created_at"]
    },
    "habits": {
        "file": os.path.join(BASE_DIR, "habits.db"),
        "table": "habits",
        "columns": ["id", "user_id", "name", "created_at"]
    },
    "habit_logs": {
        "file": os.path.join(BASE_DIR, "habits.db"),
        "table": "habit_logs",
        "columns": ["id", "habit_id", "log_date"]
    },
    "reminders": {
        "file": os.path.join(BASE_DIR, "reminders.db"),
        "table": "reminders",
        "columns": ["id", "user_id", "message", "remind_at", "triggered", "repeat_interval_minutes", "is_recurring", "last_triggered_at", "created_at"]
    }
}

_vault_lock = threading.RLock()

def _serialized(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        with _vault_lock:
            return func(*args, **kwargs)
    return wrapped

@_serialized
def read_snapshot() -> dict:
    """Read every database without changing it or triggering a cloud write."""
    vault = {"timestamp": datetime.now().isoformat(), "tables": {}}
    for db_path in dict.fromkeys(info["file"] for info in DATABASES.values()):
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Missing database: {os.path.basename(db_path)}")
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            for key, info in DATABASES.items():
                if info["file"] == db_path:
                    rows = conn.execute(f"SELECT * FROM {info['table']} ORDER BY id").fetchall()
                    vault["tables"][key] = [dict(row) for row in rows]
    return vault

@_serialized
def backup_all_databases() -> dict:
    """Atomically snapshot every table; preserve the last vault if a read fails.

    The vault must be on persistent storage to survive container replacement.
    """
    temp_path = None
    try:
        vault = read_snapshot()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=BASE_DIR,
                                         prefix="vault-", suffix=".tmp", delete=False) as f:
            temp_path = f.name
            json.dump(vault, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, VAULT_FILE)
    except Exception as exc:
        if config.SHEETS_DURABLE_STORAGE:
            import sheets_store
            sheets_store.mark_pending()
        logger.error("Backup failed; previous vault preserved: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    if config.SHEETS_DURABLE_STORAGE:
        import sheets_store
        result = sheets_store.persist(vault)
        if result["status"] != "success":
            return result
    else:
        try:
            import sheets_service
            sheets_service.trigger_background_sync()
        except Exception as exc:
            logger.debug("Sheets sync trigger: %s", exc)
    return {
        "status": "success",
        "total_records": sum(len(rows) for rows in vault["tables"].values()),
        "vault_file": VAULT_FILE,
        "timestamp": vault["timestamp"],
    }

@_serialized
def restore_all_databases() -> dict:
    """Restore only databases missing at process startup, never merge stale rows.

    Existing SQLite files remain authoritative, including deliberately empty tables.
    Older vaults without habit_logs remain readable.
    """
    if not os.path.exists(VAULT_FILE):
        return {"status": "no_backup_found", "restored": 0}
    try:
        with open(VAULT_FILE, encoding="utf-8") as f:
            tables = json.load(f)["tables"]
        if not isinstance(tables, dict):
            raise ValueError("Invalid vault tables")
    except Exception as exc:
        return {"status": "read_error", "error": str(exc)}

    restored_counts = {}
    errors = {}
    for name in sorted(config.MISSING_DATABASES.copy()):
        info = DATABASES.get(name)
        if info is None or name not in tables:
            continue
        try:
            # Import initializes a missing database even outside bot.main().
            import importlib
            service = importlib.import_module(f"{name}_service")
            service.init_db()
            with closing(sqlite3.connect(info["file"])) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                with conn:
                    keys = [key for key, meta in DATABASES.items() if meta["file"] == info["file"]]
                    # Never overwrite records written since initial startup.
                    if any(conn.execute(f"SELECT COUNT(*) FROM {DATABASES[key]['table']}").fetchone()[0] for key in keys):
                        config.MISSING_DATABASES.discard(name)
                        continue
                    counts = {}
                    for key in keys:
                        meta = DATABASES[key]
                        counts[key] = 0
                        for record in tables.get(key, []):
                            cols = [col for col in meta["columns"] if col in record]
                            if not cols:
                                raise ValueError(f"Invalid record for {key}")
                            placeholders = ", ".join("?" for _ in cols)
                            conn.execute(
                                f"INSERT INTO {meta['table']} ({', '.join(cols)}) VALUES ({placeholders})",
                                [record[col] for col in cols],
                            )
                            counts[key] += 1
                    # Due reminders stay pending: the delivery job must send them.
                restored_counts.update(counts)
            config.MISSING_DATABASES.discard(name)
        except Exception as exc:
            errors[name] = str(exc)
            logger.error("Could not restore %s: %s", name, exc)
    return {"status": "error" if errors else "restored", "restored_counts": restored_counts, "errors": errors}

def get_vault_status() -> dict:
    """
    Inspects active SQLite rows vs backup snapshot.
    """
    db_counts = {}
    for key, info in DATABASES.items():
        db_path = info["file"]
        table_name = info["table"]
        count = 0
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                conn.close()
            except Exception:
                count = 0
        db_counts[key] = count

    vault_count = 0
    vault_time = "Never"
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                v = json.load(f)
                vault_time = v.get("timestamp", "Unknown")
                vault_count = sum(len(rows) for rows in v.get("tables", {}).values())
        except Exception:
            pass

    return {
        "active_sqlite_records": db_counts,
        "vault_records": vault_count,
        "last_backup": vault_time
    }
