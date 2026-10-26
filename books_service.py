import sqlite3
import os
from datetime import datetime
import config

DB_FILE = os.path.join(os.path.dirname(__file__), "books.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 5484600217,
            title TEXT NOT NULL,
            author TEXT,
            status TEXT DEFAULT 'Reading',
            current_page INTEGER DEFAULT 0,
            total_pages INTEGER DEFAULT 0,
            rating REAL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        c.execute("ALTER TABLE books ADD COLUMN user_id INTEGER DEFAULT 5484600217")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

def add_book(title: str, author: str = "", status: str = "Reading", notes: str = "", total_pages: int = 0, user_id: int = None) -> dict:
    if user_id is None:
        user_id = config.get_current_user_id()
    try:
        total_pages = int(float(total_pages))
    except Exception:
        total_pages = 0
    status_clean = status.strip().title() if status else "Reading"
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO books (user_id, title, author, status, notes, total_pages)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, title.strip(), author.strip(), status_clean, notes.strip(), total_pages))
    b_id = c.lastrowid
    conn.commit()
    conn.close()
    
    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass

    return {
        "id": b_id,
        "title": title.strip(),
        "author": author.strip(),
        "status": status_clean,
        "notes": notes.strip(),
        "status_message": f"Added '{title}' by {author or 'Unknown'} to your books collection (Status: {status_clean})."
    }

def update_book_progress(title: str, current_page: int, notes: str = "", status: str = "", user_id: int = None) -> dict:
    if user_id is None:
        user_id = config.get_current_user_id()
    try:
        current_page = int(float(current_page))
    except Exception:
        current_page = 0
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, total_pages, notes FROM books WHERE user_id = ? AND LOWER(title) LIKE ? LIMIT 1", (user_id, f"%{title.strip().lower()}%"))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return {"error": f"Book '{title}' not found in your library."}
        
    b_id, b_title, b_tot, existing_notes = row
    new_notes = (existing_notes + "\n" + notes).strip() if notes else existing_notes
    new_status = status.strip().title() if status else ("Completed" if b_tot > 0 and current_page >= b_tot else "Reading")
    
    c.execute("""
        UPDATE books
        SET current_page = ?, notes = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (current_page, new_notes, new_status, b_id))
    conn.commit()
    conn.close()
    
    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass

    return {
        "id": b_id,
        "title": b_title,
        "current_page": current_page,
        "status": new_status,
        "status_message": f"Updated progress on '{b_title}' to page {current_page} (Status: {new_status})."
    }

def list_books(status: str = "", user_id: int = None) -> list:
    if user_id is None:
        user_id = config.get_current_user_id()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if status and status.strip():
        c.execute("""
            SELECT id, title, author, status, current_page, total_pages, rating, notes
            FROM books WHERE user_id = ? AND LOWER(status) = LOWER(?) ORDER BY id DESC
        """, (user_id, status.strip()))
    else:
        c.execute("""
            SELECT id, title, author, status, current_page, total_pages, rating, notes
            FROM books WHERE user_id = ? ORDER BY id DESC LIMIT 20
        """, (user_id,))
    rows = c.fetchall()
    conn.close()
    
    return [{
        "id": r[0], "title": r[1], "author": r[2], "status": r[3],
        "current_page": r[4], "total_pages": r[5], "rating": r[6], "notes": r[7]
    } for r in rows]

def search_books(query: str, user_id: int = None) -> list:
    if user_id is None:
        user_id = config.get_current_user_id()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    q = f"%{query.strip().lower()}%"
    c.execute("""
        SELECT id, title, author, status, current_page, total_pages, rating, notes
        FROM books
        WHERE user_id = ? AND (LOWER(title) LIKE ? OR LOWER(author) LIKE ? OR LOWER(notes) LIKE ?)
        ORDER BY id DESC LIMIT 10
    """, (user_id, q, q, q))
    rows = c.fetchall()
    conn.close()
    return [{
        "id": r[0], "title": r[1], "author": r[2], "status": r[3],
        "current_page": r[4], "total_pages": r[5], "rating": r[6], "notes": r[7]
    } for r in rows]
