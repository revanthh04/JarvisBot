import sqlite3
import os
from datetime import datetime, date, timedelta

DB_FILE = os.path.join(os.path.dirname(__file__), "habits.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at DATE DEFAULT CURRENT_DATE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            log_date DATE NOT NULL,
            UNIQUE(habit_id, log_date),
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

init_db()

def add_habit(name: str) -> dict:
    name = name.strip()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO habits (name) VALUES (?)", (name,))
        conn.commit()
        habit_id = cursor.lastrowid
        res = {"success": True, "id": habit_id, "name": name, "message": f"Habit '{name}' added."}
    except sqlite3.IntegrityError:
        res = {"success": False, "message": f"Habit '{name}' already exists."}
    finally:
        conn.close()
    return res

def log_habit(name: str, log_date: str = None) -> dict:
    if not log_date:
        log_date = date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM habits WHERE LOWER(name) = LOWER(?)", (name.strip(),))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO habits (name) VALUES (?)", (name.strip(),))
        habit_id = cursor.lastrowid
        habit_name = name.strip()
    else:
        habit_id, habit_name = row

    try:
        cursor.execute("INSERT INTO habit_logs (habit_id, log_date) VALUES (?, ?)", (habit_id, log_date))
        conn.commit()
        res = {"success": True, "message": f"Logged completion for habit '{habit_name}' on {log_date}."}
    except sqlite3.IntegrityError:
        res = {"success": True, "message": f"Habit '{habit_name}' was already logged for {log_date}."}
    finally:
        conn.close()
    return res

def get_habit_streaks() -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM habits")
    habits = cursor.fetchall()
    results = []
    today = date.today()

    for h_id, h_name in habits:
        cursor.execute("SELECT log_date FROM habit_logs WHERE habit_id = ? ORDER BY log_date DESC", (h_id,))
        logs = {r[0] for r in cursor.fetchall()}
        
        # Calculate streak
        streak = 0
        cur_day = today
        # Check if completed today, if not check starting yesterday
        if cur_day.isoformat() not in logs:
            cur_day = cur_day - timedelta(days=1)
            
        while cur_day.isoformat() in logs:
            streak += 1
            cur_day = cur_day - timedelta(days=1)

        completed_today = today.isoformat() in logs
        results.append({
            "id": h_id,
            "name": h_name,
            "streak": streak,
            "completed_today": completed_today
        })
    conn.close()
    return results

def list_habits() -> list:
    return get_habit_streaks()
