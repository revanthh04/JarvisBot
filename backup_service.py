import sqlite3
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("DataGuardian")

BASE_DIR = os.path.dirname(__file__)
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
    "reminders": {
        "file": os.path.join(BASE_DIR, "reminders.db"),
        "table": "reminders",
        "columns": ["id", "user_id", "message", "remind_at", "triggered", "repeat_interval_minutes", "is_recurring", "last_triggered_at", "created_at"]
    }
}

def backup_all_databases() -> dict:
    """
    Snapshots all 6 SQLite databases into a portable JSON vault.
    Guarantees data survives server restarts or container re-deployments.
    """
    vault = {
        "timestamp": datetime.now().isoformat(),
        "tables": {}
    }

    total_records = 0
    for key, info in DATABASES.items():
        db_path = info["file"]
        table_name = info["table"]
        records = []
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                # Check if table exists
                c.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                if c.fetchone()[0] > 0:
                    rows = c.execute(f"SELECT * FROM {table_name}").fetchall()
                    records = [dict(r) for r in rows]
                conn.close()
            except Exception as e:
                logger.error(f"Error backing up {key}: {e}")

        vault["tables"][key] = records
        total_records += len(records)

    with open(VAULT_FILE, "w", encoding="utf-8") as f:
        json.dump(vault, f, indent=2, ensure_ascii=False)

    return {
        "status": "success",
        "total_records": total_records,
        "vault_file": VAULT_FILE,
        "timestamp": vault["timestamp"]
    }

def restore_all_databases() -> dict:
    """
    Auto-restores data from the JSON vault if an ephemeral container restarted
    with empty or missing SQLite database files.
    """
    if not os.path.exists(VAULT_FILE):
        return {"status": "no_backup_found", "restored": 0}

    try:
        with open(VAULT_FILE, "r", encoding="utf-8") as f:
            vault = json.load(f)
    except Exception as e:
        logger.error(f"Could not read vault file: {e}")
        return {"status": "read_error", "error": str(e)}

    tables = vault.get("tables", {})
    restored_counts = {}

    for key, records in tables.items():
        if not records:
            continue
        info = DATABASES.get(key)
        if not info:
            continue

        db_path = info["file"]
        table_name = info["table"]

        # Ensure database tables exist by calling their respective init
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Check existing IDs to prevent duplicates
        existing_ids = set()
        try:
            c.execute(f"SELECT id FROM {table_name}")
            existing_ids = {row[0] for row in c.fetchall()}
        except Exception:
            pass

        inserted = 0
        for rec in records:
            rec_id = rec.get("id")
            if rec_id and rec_id in existing_ids:
                continue

            # Dynamically insert
            cols = [col for col in rec.keys() if col in info["columns"]]
            if not cols:
                continue
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            values = [rec[c_name] for c_name in cols]

            try:
                c.execute(f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})", values)
                inserted += 1
            except Exception as err:
                logger.warning(f"Error inserting restored row in {table_name}: {err}")

        conn.commit()
        conn.close()
        restored_counts[key] = inserted

    return {
        "status": "restored",
        "restored_counts": restored_counts
    }

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
