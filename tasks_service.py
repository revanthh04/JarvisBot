import sqlite3
import os
from datetime import datetime
import config

DB_FILE = os.path.join(os.path.dirname(__file__), "tasks.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 5484600217,
            title TEXT NOT NULL,
            due_date TEXT,
            completed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN user_id INTEGER DEFAULT 5484600217")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

def add_task(title: str, due_date: str = None, user_id: int = None) -> dict:
    user_id = config.resolve_user_id(user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (user_id, title, due_date) VALUES (?, ?, ?)", (user_id, title.strip(), due_date))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass
    return {"id": task_id, "title": title.strip(), "due_date": due_date, "completed": False}

def list_tasks(completed: bool = False, user_id: int = None) -> list:
    user_id = config.resolve_user_id(user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if completed is None:
        cursor.execute("SELECT id, title, due_date, completed, created_at FROM tasks WHERE user_id = ? ORDER BY id ASC", (user_id,))
    else:
        cursor.execute("SELECT id, title, due_date, completed, created_at FROM tasks WHERE user_id = ? AND completed = ? ORDER BY id ASC", (user_id, 1 if completed else 0))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "due_date": r[2], "completed": bool(r[3]), "created_at": r[4]} for r in rows]

def complete_task(task_id, user_id: int = None) -> bool:
    user_id = config.resolve_user_id(user_id)
    try:
        task_id = int(float(task_id))
    except Exception:
        return False
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET completed = 1 WHERE id = ? AND user_id = ?", (task_id, user_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass
    return affected

def delete_task(task_id, user_id: int = None) -> bool:
    user_id = config.resolve_user_id(user_id)
    try:
        task_id = int(float(task_id))
    except Exception:
        return False
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass
    return affected
