import sqlite3
import os
import re
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
            repeat_interval_minutes INTEGER DEFAULT 0,
            is_recurring BOOLEAN DEFAULT 0,
            last_triggered_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Check for missing columns in case of existing table
    c.execute("PRAGMA table_info(reminders)")
    cols = [col[1] for col in c.fetchall()]
    if "repeat_interval_minutes" not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN repeat_interval_minutes INTEGER DEFAULT 0")
    if "is_recurring" not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN is_recurring BOOLEAN DEFAULT 0")
    if "last_triggered_at" not in cols:
        c.execute("ALTER TABLE reminders ADD COLUMN last_triggered_at TEXT")
    conn.commit()
    conn.close()

init_db()

def _clean_reminder_message(raw_msg: str) -> str:
    msg = raw_msg.strip()
    # Strip common leading conversational phrases
    patterns_strip = [
        r'^(?:so\s+)?(?:from\s+here\s+on\s+(?:words|out)\s+)?remind\s+(?:me\s+)?(?:to\s+|for\s+)?',
        r'^remind\s+(?:me\s+)?(?:to\s+|for\s+)?',
        r'^please\s+remind\s+(?:me\s+)?(?:to\s+|for\s+)?',
    ]
    for p in patterns_strip:
        msg = re.sub(p, '', msg, flags=re.IGNORECASE).strip()

    # Strip trailing recurring interval mentions like 'for every 20 mins', 'every 20 minutes', 'every hour'
    msg = re.sub(r'(?:\s+for)?\s+every\s+\d+\s*(?:minutes?|mins?|m|hours?|hrs?|h|days?)', '', msg, flags=re.IGNORECASE).strip()
    msg = re.sub(r'(?:\s+for)?\s+every\s+(?:hour|half(?:\s+an)?\s+hour|day)', '', msg, flags=re.IGNORECASE).strip()
    msg = re.sub(r'\s+daily\b', '', msg, flags=re.IGNORECASE).strip()

    # Strip explicit time markers like 'at 7:45', 'at 7:45 pm', 'in 15 mins'
    msg = re.sub(r'\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?', '', msg, flags=re.IGNORECASE).strip()
    msg = re.sub(r'\bin\s+\d+\s*(?:minutes?|mins?|m|hours?|hrs?|h)', '', msg, flags=re.IGNORECASE).strip()

    # Strip conversational fillers
    msg = re.sub(r'\b(?:okayy?|ok|please|thanks?)\b', '', msg, flags=re.IGNORECASE).strip()

    # Strip leading 'to ' or 'for ' if left behind
    msg = re.sub(r'^(?:to|for)\s+', '', msg, flags=re.IGNORECASE).strip()

    if not msg:
        msg = "General Reminder"
    # Capitalize first letter
    return msg[0].upper() + msg[1:] if len(msg) > 1 else msg.upper()

def create_reminder(
    message: str,
    delay_minutes: int = 0,
    time_str: str = "",
    repeat_interval_minutes: int = 0,
    is_recurring: bool = False,
    user_id: int = None
) -> dict:
    """
    Creates a one-time or recurring reminder.
    
    Parameters:
    - message: Content to remind about (e.g., 'Drink water', 'Team sync').
    - delay_minutes: Delay until first reminder in minutes.
    - time_str: Natural language time string (e.g. 'in 20 mins', 'every 20 mins', '19:45', '7:45 PM', 'every hour').
    - repeat_interval_minutes: If > 0, reminder will automatically reschedule and repeat indefinitely every N minutes until stopped.
    - is_recurring: Explicit flag for recurring reminders.
    """
    tz = config.get_tz()
    now = datetime.now(tz)
    combined_search_text = f"{message} {time_str}".lower()

    # Detect interval pattern in message or time_str
    detected_interval = 0
    match_rec_min = re.search(r'every\s+(\d+)\s*(?:minutes?|mins?|m)', combined_search_text)
    match_rec_hr = re.search(r'every\s+(\d+)\s*(?:hours?|hrs?|h)', combined_search_text)
    match_rec_every_hr = re.search(r'every\s+hour', combined_search_text)
    match_rec_half_hr = re.search(r'every\s+half(?:\s+an)?\s+hour', combined_search_text)
    match_rec_daily = re.search(r'daily|every\s+day', combined_search_text)

    if match_rec_min:
        detected_interval = int(match_rec_min.group(1))
    elif match_rec_hr:
        detected_interval = int(match_rec_hr.group(1)) * 60
    elif match_rec_half_hr:
        detected_interval = 30
    elif match_rec_every_hr:
        detected_interval = 60
    elif match_rec_daily:
        detected_interval = 1440

    if detected_interval > 0:
        is_recurring = True
        repeat_interval_minutes = detected_interval

    if repeat_interval_minutes > 0:
        is_recurring = True

    # If time_str was not passed, extract from message
    if not time_str and not delay_minutes:
        match_at = re.search(r'\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', message, flags=re.IGNORECASE)
        match_in_m = re.search(r'\bin\s+(\d+)\s*(?:minutes?|mins?|m)', message, flags=re.IGNORECASE)
        match_in_h = re.search(r'\bin\s+(\d+)\s*(?:hours?|hrs?|h)', message, flags=re.IGNORECASE)
        if match_at:
            time_str = match_at.group(1)
        elif match_in_h:
            delay_minutes = int(match_in_h.group(1)) * 60
        elif match_in_m:
            delay_minutes = int(match_in_m.group(1))

    remind_dt = None

    if delay_minutes and delay_minutes > 0:
        remind_dt = now + timedelta(minutes=delay_minutes)
    elif time_str:
        time_clean = time_str.strip().lower()
        has_am = bool(re.search(r'\bam\b', time_clean))
        has_pm = bool(re.search(r'\bpm\b', time_clean))

        match_min = re.search(r'(\d+)\s*(?:m|min|minute|minutes)', time_clean)
        match_hr = re.search(r'(\d+)\s*(?:h|hr|hour|hours)', time_clean)

        if match_hr and not match_rec_hr:
            hrs = int(match_hr.group(1))
            remind_dt = now + timedelta(hours=hrs)
        elif match_min and not match_rec_min:
            mins = int(match_min.group(1))
            remind_dt = now + timedelta(minutes=mins)
        else:
            time_upper = time_clean.upper()
            for fmt in ["%H:%M", "%I:%M %p", "%I:%M%p", "%I %p", "%H"]:
                try:
                    parsed = datetime.strptime(time_upper, fmt)
                    h = parsed.hour
                    m = parsed.minute

                    # Smart 12-hour resolution if AM/PM was omitted
                    if not has_am and not has_pm and h < 12:
                        dt_am = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        dt_pm = now.replace(hour=h + 12, minute=m, second=0, microsecond=0)
                        if dt_am < now and dt_pm >= now:
                            remind_dt = dt_pm  # Target is this afternoon/evening!
                        elif dt_am >= now:
                            remind_dt = dt_am  # Target is this morning!
                        else:
                            remind_dt = dt_am + timedelta(days=1)  # Both today have passed, target tomorrow morning
                    else:
                        remind_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        if remind_dt < now:
                            remind_dt = remind_dt + timedelta(days=1)
                    break
                except ValueError:
                    continue

            if not remind_dt:
                for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p"]:
                    try:
                        parsed = datetime.strptime(time_upper, fmt)
                        remind_dt = tz.localize(parsed)
                        break
                    except ValueError:
                        continue

    # If recurring and no specific first time specified, first trigger fires in repeat_interval_minutes
    if not remind_dt:
        if is_recurring and repeat_interval_minutes > 0:
            remind_dt = now + timedelta(minutes=repeat_interval_minutes)
        else:
            remind_dt = now + timedelta(minutes=10)

    clean_msg = _clean_reminder_message(message)
    user_id = config.resolve_user_id(user_id)
    remind_iso = remind_dt.isoformat()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO reminders (user_id, message, remind_at, triggered, repeat_interval_minutes, is_recurring)
        VALUES (?, ?, ?, 0, ?, ?)
    """, (user_id, clean_msg, remind_iso, repeat_interval_minutes, 1 if is_recurring else 0))
    rem_id = c.lastrowid
    conn.commit()
    conn.close()

    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass

    formatted_time = remind_dt.strftime("%I:%M %p")
    if is_recurring:
        status_text = (
            f"Recurring reminder active for '{clean_msg}'. "
            f"Next reminder at {formatted_time}, repeating every {repeat_interval_minutes} minutes."
        )
    else:
        status_text = f"Reminder set for '{clean_msg}' at {formatted_time}."

    return {
        "id": rem_id,
        "message": clean_msg,
        "remind_at": formatted_time,
        "is_recurring": is_recurring,
        "repeat_interval_minutes": repeat_interval_minutes,
        "status": status_text
    }

def get_due_reminders() -> list:
    """
    Returns all reminders that are due to trigger right now.
    """
    tz = config.get_tz()
    now_iso = datetime.now(tz).isoformat()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, message, remind_at, repeat_interval_minutes, is_recurring, last_triggered_at
        FROM reminders
        WHERE triggered = 0 AND remind_at <= ?
    """, (now_iso,))
    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "user_id": r[1],
            "message": r[2],
            "remind_at": r[3],
            "repeat_interval_minutes": r[4] or 0,
            "is_recurring": bool(r[5]),
            "last_triggered_at": r[6]
        }
        for r in rows
    ]

def reschedule_recurring_reminder(reminder_id: int, interval_minutes: int) -> str:
    """
    Advances a recurring reminder to trigger again after interval_minutes.
    Keeps triggered=0 so it repeats indefinitely.
    """
    tz = config.get_tz()
    now = datetime.now(tz)
    next_remind_dt = now + timedelta(minutes=interval_minutes)
    next_remind_iso = next_remind_dt.isoformat()
    now_iso = now.isoformat()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        UPDATE reminders 
        SET remind_at = ?, last_triggered_at = ?, triggered = 0
        WHERE id = ?
    """, (next_remind_iso, now_iso, reminder_id))
    conn.commit()
    conn.close()

    return next_remind_dt.strftime("%I:%M %p")

def mark_reminder_triggered(reminder_id: int):
    """
    Marks a one-time reminder as triggered so it will not fire again.
    """
    tz = config.get_tz()
    now_iso = datetime.now(tz).isoformat()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE reminders SET triggered = 1, last_triggered_at = ? WHERE id = ?", (now_iso, reminder_id))
    conn.commit()
    conn.close()

def stop_recurring_reminders(keyword: str = "", user_id: int = None) -> dict:
    """
    Stops/disables recurring reminders.
    If keyword is provided (e.g. 'water'), stops recurring reminders matching that keyword.
    If keyword is empty or 'all', stops all recurring reminders for the active user.
    """
    user_id = config.resolve_user_id(user_id)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if keyword and keyword.strip().lower() != "all":
        search_kw = f"%{keyword.strip().lower()}%"
        c.execute("""
            UPDATE reminders 
            SET triggered = 1 
            WHERE user_id = ? AND triggered = 0 AND is_recurring = 1 AND LOWER(message) LIKE ?
        """, (user_id, search_kw))
    else:
        c.execute("""
            UPDATE reminders 
            SET triggered = 1 
            WHERE user_id = ? AND triggered = 0 AND is_recurring = 1
        """, (user_id,))
    
    rows_affected = c.rowcount
    conn.commit()
    conn.close()

    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass

    target_str = f"'{keyword}'" if keyword and keyword != "all" else "all"
    if rows_affected > 0:
        return {
            "success": True,
            "count": rows_affected,
            "status_message": f"Successfully stopped {rows_affected} recurring reminder(s) for {target_str}."
        }
    else:
        return {
            "success": False,
            "count": 0,
            "status_message": f"No active recurring reminders found matching {target_str}."
        }

def delete_reminder(reminder_id: int, user_id: int = None) -> dict:
    """
    Deletes a reminder by ID.
    """
    user_id = config.resolve_user_id(user_id)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
    rows_affected = c.rowcount
    conn.commit()
    conn.close()

    try:
        import backup_service
        backup_service.backup_all_databases()
    except Exception:
        pass

    if rows_affected > 0:
        return {"success": True, "status_message": f"Reminder #{reminder_id} deleted."}
    return {"success": False, "status_message": f"Reminder #{reminder_id} not found."}

def list_active_reminders(user_id: int = None) -> list:
    """
    Lists all currently active (untriggered) reminders for the user.
    """
    user_id = config.resolve_user_id(user_id)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT id, message, remind_at, repeat_interval_minutes, is_recurring
        FROM reminders 
        WHERE user_id = ? AND triggered = 0 
        ORDER BY remind_at ASC
    """, (user_id,))
    rows = c.fetchall()
    conn.close()

    result = []
    tz = config.get_tz()
    for r in rows:
        rem_id, msg, r_at, interval, is_rec = r
        try:
            dt = datetime.fromisoformat(r_at)
            formatted = dt.strftime("%I:%M %p on %b %d")
        except Exception:
            formatted = r_at

        recurrence_desc = f"Repeats every {interval} mins" if is_rec and interval > 0 else "One-time"
        result.append({
            "id": rem_id,
            "message": msg,
            "remind_at": formatted,
            "raw_remind_at": r_at,
            "is_recurring": bool(is_rec),
            "repeat_interval_minutes": interval or 0,
            "recurrence": recurrence_desc
        })
    return result
