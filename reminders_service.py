import sqlite3
import os
from datetime import datetime, timedelta
import pytz
import config

DB_FILE = os.path.join(os.path.dirname(__file__), "reminders.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            triggered BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def create_reminder(message: str, delay_minutes: int = 0, time_str: str = "", user_id: int = None) -> dict:
    """
    Creates a reminder.
    Either provide delay_minutes (e.g. 15 for 15 minutes from now)
    OR provide time_str (e.g. '13:20', '1:20 PM', 'in 15 minutes', '1 hour')
    """
    import re
    tz = config.get_tz()
    now = datetime.now(tz)

    remind_dt = None

    if delay_minutes and delay_minutes > 0:
        remind_dt = now + timedelta(minutes=delay_minutes)
    elif time_str:
        time_clean = time_str.strip().lower()
        
        # Check for relative minutes: e.g. "in 15 mins", "15 minutes", "10m"
        match_min = re.search(r'(\d+)\s*(?:m|min|minute|minutes)', time_clean)
        match_hr = re.search(r'(\d+)\s*(?:h|hr|hour|hours)', time_clean)
        
        if match_hr:
            hrs = int(match_hr.group(1))
            remind_dt = now + timedelta(hours=hrs)
        elif match_min:
            mins = int(match_min.group(1))
            remind_dt = now + timedelta(minutes=mins)
        else:
            time_upper = time_clean.upper()
            for fmt in ["%H:%M", "%I:%M %p", "%I:%M%p", "%I %p", "%Y-%m-%d %H:%M"]:
                try:
                    parsed = datetime.strptime(time_upper, fmt)
                    if fmt in ["%H:%M", "%I:%M %p", "%I:%M%p", "%I %p"]:
                        remind_dt = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
                        if remind_dt < now:
                            remind_dt = remind_dt + timedelta(days=1)
                    else:
                        remind_dt = tz.localize(parsed)
                    break
                except ValueError:
                    continue

    if not remind_dt:
        remind_dt = now + timedelta(minutes=10)

    if user_id is None:
        user_id = config.get_current_user_id()
    remind_iso = remind_dt.isoformat()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO reminders (user_id, message, remind_at, triggered)
        VALUES (?, ?, ?, 0)
    """, (user_id, message.strip(), remind_iso))
    rem_id = c.lastrowid
    conn.commit()
    conn.close()

    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass

    formatted_time = remind_dt.strftime("%I:%M %p on %b %d")
    return {
        "id": rem_id,
        "message": message,
        "remind_at": formatted_time,
        "status": f"Reminder set for '{message}' at {formatted_time}."
    }

def get_due_reminders() -> list:
    tz = config.get_tz()
    now_iso = datetime.now(tz).isoformat()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, message, remind_at
        FROM reminders
        WHERE triggered = 0 AND remind_at <= ?
    """, (now_iso,))
    rows = c.fetchall()
    conn.close()

    return [{"id": r[0], "user_id": r[1], "message": r[2], "remind_at": r[3]} for r in rows]

def mark_reminder_triggered(reminder_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE reminders SET triggered = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def list_active_reminders(user_id: int = None) -> list:
    if user_id is None:
        user_id = config.get_current_user_id()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, message, remind_at FROM reminders WHERE user_id = ? AND triggered = 0 ORDER BY remind_at ASC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "message": r[1], "remind_at": r[2]} for r in rows]
