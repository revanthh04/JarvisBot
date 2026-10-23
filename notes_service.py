import sqlite3
import os
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(__file__), "notes.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT NOT NULL,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def add_note(content: str, title: str = "", tags: str = "") -> dict:
    if not title:
        title = content[:30] + ("..." if len(content) > 30 else "")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO notes (title, content, tags) VALUES (?, ?, ?)", (title, content, tags))
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": note_id, "title": title, "content": content, "tags": tags}

def search_notes(query: str) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    search = f"%{query}%"
    cursor.execute("""
        SELECT id, title, content, tags, created_at FROM notes
        WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
        ORDER BY created_at DESC LIMIT 10
    """, (search, search, search))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "content": r[2], "tags": r[3], "created_at": r[4]} for r in rows]

def list_notes(limit: int = 10) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, tags, created_at FROM notes ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "content": r[2], "tags": r[3], "created_at": r[4]} for r in rows]

def delete_note(note_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected
