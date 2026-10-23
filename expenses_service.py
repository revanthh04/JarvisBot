import sqlite3
import os
from datetime import datetime, date
import json

DB_FILE = os.path.join(os.path.dirname(__file__), "expenses.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            expense_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def log_expense(amount: float, category: str = "General", description: str = "", expense_date: str = None) -> dict:
    if not expense_date:
        expense_date = date.today().isoformat()
    try:
        amount_num = float(amount)
    except Exception:
        amount_num = 0.0

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expenses (amount, category, description, expense_date)
        VALUES (?, ?, ?, ?)
    """, (amount_num, category.strip().title(), description.strip(), expense_date.strip()))
    exp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": exp_id,
        "amount": amount_num,
        "category": category.strip().title(),
        "description": description.strip(),
        "date": expense_date.strip(),
        "status": f"Logged ₹{amount_num:,.2f} for '{description}' under {category} on {expense_date}."
    }

def get_monthly_summary(month=None, year=None) -> dict:
    today = date.today()
    try:
        month_int = int(float(month)) if month else today.month
    except Exception:
        month_int = today.month

    try:
        year_int = int(float(year)) if year else today.year
    except Exception:
        year_int = today.year

    month_str = f"{year_int:04d}-{month_int:02d}-%"
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, SUM(amount), COUNT(*)
        FROM expenses
        WHERE expense_date LIKE ?
        GROUP BY category
    """, (month_str,))
    rows = cursor.fetchall()

    cursor.execute("SELECT SUM(amount) FROM expenses WHERE expense_date LIKE ?", (month_str,))
    total_row = cursor.fetchone()
    total = total_row[0] if total_row and total_row[0] else 0.0

    conn.close()
    breakdown = [{"category": r[0], "total": round(r[1], 2), "count": r[2]} for r in rows]
    return {
        "month": f"{year_int:04d}-{month_int:02d}",
        "total_expenditure": round(total, 2),
        "by_category": breakdown
    }

def search_expenses(category: str = "", query: str = "", date_str: str = "") -> dict:
    """Search expenses by category (e.g. Food), text keyword, or specific date."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    sql = "SELECT id, amount, category, description, expense_date FROM expenses WHERE 1=1"
    params = []
    
    if category and category.strip():
        sql += " AND LOWER(category) LIKE ?"
        params.append(f"%{category.strip().lower()}%")
        
    if query and query.strip():
        sql += " AND (LOWER(description) LIKE ? OR LOWER(category) LIKE ?)"
        q = f"%{query.strip().lower()}%"
        params.extend([q, q])
        
    if date_str and date_str.strip():
        sql += " AND expense_date = ?"
        params.append(date_str.strip())
        
    sql += " ORDER BY expense_date DESC, id DESC LIMIT 50"
    
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    
    total = sum(r[1] for r in rows)
    entries = [{"id": r[0], "amount": r[1], "category": r[2], "description": r[3], "date": r[4]} for r in rows]
    
    return {
        "count": len(entries),
        "total_amount": round(total, 2),
        "entries": entries
    }

def get_expenses_by_date(date_str: str = None) -> list:
    if not date_str:
        date_str = date.today().isoformat()
    return search_expenses(date_str=date_str).get("entries", [])

def get_recent_expenses(limit: int = 10) -> list:
    try:
        limit = int(float(limit))
    except Exception:
        limit = 10
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, category, description, expense_date FROM expenses ORDER BY expense_date DESC, id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1], "category": r[2], "description": r[3], "date": r[4]} for r in rows]
