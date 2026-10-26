import sqlite3
import os
from datetime import datetime, date, timedelta
import re
import json
import config

DB_FILE = os.path.join(os.path.dirname(__file__), "expenses.db")

def normalize_expense_date(d_str: str = None) -> str:
    """
    Converts any natural language date (e.g. 'yesterday', 'today', '2 days ago',
    'October 22, 2026', '22/10/2026') into standard ISO YYYY-MM-DD.
    """
    tz = config.get_tz()
    today = datetime.now(tz).date()
    if not d_str or not str(d_str).strip():
        return today.isoformat()
    
    s = str(d_str).strip().lower()
    if s in ["today", "tonight", "now"]:
        return today.isoformat()
    if s in ["yesterday"]:
        return (today - timedelta(days=1)).isoformat()
    if s in ["day before yesterday"]:
        return (today - timedelta(days=2)).isoformat()
    if s in ["tomorrow"]:
        return (today + timedelta(days=1)).isoformat()
    
    m_ago = re.search(r'(\d+)\s*days?\s*ago', s)
    if m_ago:
        return (today - timedelta(days=int(m_ago.group(1)))).isoformat()
        
    for fmt in [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
        "%B %d", "%b %d"
    ]:
        try:
            dt = datetime.strptime(str(d_str).strip(), fmt)
            if fmt in ["%B %d", "%b %d"]:
                dt = dt.replace(year=today.year)
            return dt.date().isoformat()
        except ValueError:
            pass
            
    return today.isoformat()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 5484600217,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            expense_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Self-healing migration for user_id and legacy relative dates
    try:
        cursor.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER DEFAULT 5484600217")
    except Exception:
        pass
    try:
        cursor.execute("UPDATE expenses SET expense_date = DATE(created_at, '-1 day') WHERE LOWER(expense_date) = 'yesterday'")
        cursor.execute("UPDATE expenses SET expense_date = DATE(created_at) WHERE LOWER(expense_date) IN ('today', 'now')")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

def log_expense(amount: float, category: str = "General", description: str = "", expense_date: str = None, user_id: int = None) -> dict:
    if user_id is None:
        user_id = config.get_current_user_id()
    clean_date = normalize_expense_date(expense_date)
    try:
        amount_num = float(amount)
    except Exception:
        amount_num = 0.0

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expenses (user_id, amount, category, description, expense_date)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, amount_num, category.strip().title(), description.strip(), clean_date))
    exp_id = cursor.lastrowid
    conn.commit()
    conn.close()

    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass

    return {
        "id": exp_id,
        "amount": amount_num,
        "category": category.strip().title(),
        "description": description.strip(),
        "date": clean_date,
        "status": f"Logged ₹{amount_num:,.2f} for '{description}' under {category} on {clean_date}."
    }

def get_monthly_summary(month=None, year=None, user_id: int = None) -> dict:
    if user_id is None:
        user_id = config.get_current_user_id()
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
        WHERE user_id = ? AND expense_date LIKE ?
        GROUP BY category
    """, (user_id, month_str))
    rows = cursor.fetchall()

    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND expense_date LIKE ?", (user_id, month_str))
    total_row = cursor.fetchone()
    total = total_row[0] if total_row and total_row[0] else 0.0

    conn.close()
    breakdown = [{"category": r[0], "total": round(r[1], 2), "count": r[2]} for r in rows]
    return {
        "month": f"{year_int:04d}-{month_int:02d}",
        "total_expenditure": round(total, 2),
        "by_category": breakdown
    }

def search_expenses(category: str = "", query: str = "", date_str: str = "", user_id: int = None) -> dict:
    """Search expenses by category (e.g. Food), text keyword, or specific date."""
    if user_id is None:
        user_id = config.get_current_user_id()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    sql = "SELECT id, amount, category, description, expense_date FROM expenses WHERE user_id = ?"
    params = [user_id]
    
    if category and category.strip():
        sql += " AND LOWER(category) LIKE ?"
        params.append(f"%{category.strip().lower()}%")
        
    if query and query.strip():
        sql += " AND (LOWER(description) LIKE ? OR LOWER(category) LIKE ?)"
        q = f"%{query.strip().lower()}%"
        params.extend([q, q])
        
    if date_str and str(date_str).strip():
        norm_date = normalize_expense_date(date_str)
        sql += " AND (expense_date = ? OR expense_date = ?)"
        params.extend([norm_date, str(date_str).strip()])
        
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

def get_expenses_by_date(date_str: str = None, user_id: int = None) -> list:
    norm_date = normalize_expense_date(date_str)
    return search_expenses(date_str=norm_date, user_id=user_id).get("entries", [])

def get_recent_expenses(limit: int = 10, user_id: int = None) -> list:
    if user_id is None:
        user_id = config.get_current_user_id()
    try:
        limit = int(float(limit))
    except Exception:
        limit = 10
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, category, description, expense_date FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, id DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1], "category": r[2], "description": r[3], "date": r[4]} for r in rows]
