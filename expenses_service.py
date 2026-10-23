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
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expenses (amount, category, description, expense_date)
        VALUES (?, ?, ?, ?)
    """, (float(amount), category.strip(), description.strip(), expense_date))
    exp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": exp_id,
        "amount": amount,
        "category": category,
        "description": description,
        "date": expense_date
    }

def get_monthly_summary(month: int = None, year: int = None) -> dict:
    today = date.today()
    if not month:
        month = today.month
    if not year:
        year = today.year

    month_str = f"{year:04d}-{month:02d}-%"
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
        "month": f"{year:04d}-{month:02d}",
        "total_expenditure": round(total, 2),
        "by_category": breakdown
    }

def get_recent_expenses(limit: int = 10) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, category, description, expense_date FROM expenses ORDER BY expense_date DESC, id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1], "category": r[2], "description": r[3], "date": r[4]} for r in rows]
