import sqlite3
import os
from datetime import datetime
import config

DB_FILE = os.path.join(os.path.dirname(__file__), "notes.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 5484600217,
            title TEXT,
            content TEXT NOT NULL,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE notes ADD COLUMN user_id INTEGER DEFAULT 5484600217")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

def add_note(content: str, title: str = "", tags: str = "", user_id: int = None) -> dict:
    user_id = config.resolve_user_id(user_id)
    if not title:
        title = content[:30] + ("..." if len(content) > 30 else "")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO notes (user_id, title, content, tags) VALUES (?, ?, ?, ?)", (user_id, title, content, tags))
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass
    return {"id": note_id, "title": title, "content": content, "tags": tags}

def search_notes(query: str, user_id: int = None) -> list:
    user_id = config.resolve_user_id(user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    search = f"%{query}%"
    cursor.execute("""
        SELECT id, title, content, tags, created_at FROM notes
        WHERE user_id = ? AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)
        ORDER BY created_at DESC LIMIT 10
    """, (user_id, search, search, search))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "content": r[2], "tags": r[3], "created_at": r[4]} for r in rows]

def list_notes(limit: int = 10, user_id: int = None) -> list:
    user_id = config.resolve_user_id(user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, tags, created_at FROM notes WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "content": r[2], "tags": r[3], "created_at": r[4]} for r in rows]

def delete_note(note_id, user_id: int = None) -> bool:
    user_id = config.resolve_user_id(user_id)
    try:
        note_id = int(float(note_id))
    except Exception:
        return False
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass
    return affected
