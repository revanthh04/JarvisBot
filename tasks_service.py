import sqlite3
import os
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(__file__), "tasks.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_date TEXT,
            completed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def add_task(title: str, due_date: str = None) -> dict:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (title, due_date) VALUES (?, ?)", (title.strip(), due_date))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": task_id, "title": title.strip(), "due_date": due_date, "completed": False}

def list_tasks(completed: bool = False) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, due_date, completed, created_at FROM tasks WHERE completed = ? ORDER BY id ASC", (1 if completed else 0,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "due_date": r[2], "completed": bool(r[3]), "created_at": r[4]} for r in rows]

def complete_task(task_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def delete_task(task_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected
