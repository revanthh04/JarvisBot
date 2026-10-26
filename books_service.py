import sqlite3
import os
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(__file__), "books.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn.commit()
    conn.close()

init_db()

def add_book(title: str, author: str = "", status: str = "Reading", notes: str = "", total_pages: int = 0) -> dict:
    try:
        total_pages = int(float(total_pages))
    except Exception:
        total_pages = 0
    status_clean = status.strip().title() if status else "Reading"
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO books (title, author, status, notes, total_pages)
        VALUES (?, ?, ?, ?, ?)
    """, (title.strip(), author.strip(), status_clean, notes.strip(), total_pages))
    b_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return {
        "id": b_id,
        "title": title.strip(),
        "author": author.strip(),
        "status": status_clean,
        "notes": notes.strip(),
        "status_message": f"Added '{title}' by {author or 'Unknown'} to your books collection (Status: {status_clean})."
    }

def update_book_progress(title: str, current_page: int, notes: str = "", status: str = "") -> dict:
    try:
        current_page = int(float(current_page))
    except Exception:
        current_page = 0
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, total_pages, notes FROM books WHERE LOWER(title) LIKE ? LIMIT 1", (f"%{title.strip().lower()}%",))
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
    
    return {
        "id": b_id,
        "title": b_title,
        "current_page": current_page,
        "status": new_status,
        "status_message": f"Updated progress on '{b_title}' to page {current_page} (Status: {new_status})."
    }

def list_books(status: str = "") -> list:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if status and status.strip():
        c.execute("""
            SELECT id, title, author, status, current_page, total_pages, rating, notes
            FROM books WHERE LOWER(status) = LOWER(?) ORDER BY id DESC
        """, (status.strip(),))
    else:
        c.execute("""
            SELECT id, title, author, status, current_page, total_pages, rating, notes
            FROM books ORDER BY id DESC LIMIT 20
        """)
    rows = c.fetchall()
    conn.close()
    
    return [{
        "id": r[0], "title": r[1], "author": r[2], "status": r[3],
        "current_page": r[4], "total_pages": r[5], "rating": r[6], "notes": r[7]
    } for r in rows]

def search_books(query: str) -> list:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    q = f"%{query.strip().lower()}%"
    c.execute("""
        SELECT id, title, author, status, current_page, total_pages, rating, notes
        FROM books
        WHERE LOWER(title) LIKE ? OR LOWER(author) LIKE ? OR LOWER(notes) LIKE ?
        ORDER BY id DESC LIMIT 10
    """, (q, q, q))
    rows = c.fetchall()
    conn.close()
    return [{
        "id": r[0], "title": r[1], "author": r[2], "status": r[3],
        "current_page": r[4], "total_pages": r[5], "rating": r[6], "notes": r[7]
    } for r in rows]
