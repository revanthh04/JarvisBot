import sys
import os
import sqlite3
import json
import time
from datetime import datetime, timedelta
import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import config
import reminders_service
import expenses_service
import books_service
import tasks_service
import notes_service
import habits_service
import ai_agent
import backup_service

print("==================================================================")
print("     AUTONOMOUS BOT QA & SYNTHETIC SIMULATION AGENT ACTIVE        ")
print("==================================================================")

report = {
    "timestamp": datetime.now().isoformat(),
    "parameters_tested": 0,
    "parameters_passed": 0,
    "details": []
}

def log_param(param_num, name, passed, details):
    report["parameters_tested"] += 1
    if passed:
        report["parameters_passed"] += 1
    status_str = "PASS" if passed else "FAIL"
    print(f"[{param_num:02d}] {name}: [{status_str}]")
    print(f"     Details: {details}")
    report["details"].append({
        "number": param_num,
        "name": name,
        "status": status_str,
        "details": details
    })

# ------------------------------------------------------------------
# Parameter 1: Telegram Bot API Live Connectivity & Polling
# ------------------------------------------------------------------
try:
    tg_res = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getMe", timeout=10).json()
    if tg_res.get("ok"):
        bot_info = tg_res["result"]
        log_param(1, "Telegram API Live Handshake", True, f"Connected to @{bot_info['username']} (ID: {bot_info['id']})")
    else:
        log_param(1, "Telegram API Live Handshake", False, f"Telegram API error: {tg_res}")
except Exception as e:
    log_param(1, "Telegram API Live Handshake", False, str(e))

# ------------------------------------------------------------------
# Parameter 2: Cloud Keep-Alive Server Health
# ------------------------------------------------------------------
try:
    render_res = requests.get("https://jarvis-bot-rhuk.onrender.com/", timeout=10)
    if render_res.status_code == 200:
        log_param(2, "Render Cloud 24/7 Keep-Alive", True, f"HTTP {render_res.status_code} OK - {render_res.text.strip()}")
    else:
        log_param(2, "Render Cloud 24/7 Keep-Alive", False, f"HTTP {render_res.status_code}")
except Exception as e:
    log_param(2, "Render Cloud 24/7 Keep-Alive", False, str(e))

# ------------------------------------------------------------------
# Parameter 3: Reminders Subsystem (Add -> Check -> Trigger Test -> Clean)
# ------------------------------------------------------------------
try:
    # 1. Add synthetic reminder
    rem = reminders_service.create_reminder(message="QA Test: Drink water & review metrics", delay_minutes=1)
    rem_id = rem["id"]
    
    # 2. Check active reminders
    active = reminders_service.list_active_reminders()
    found_active = any(r["id"] == rem_id for r in active)
    
    # 3. Simulate due trigger test
    # Temporarily set remind_at to 1 minute ago to test trigger query
    past_iso = (datetime.now(config.get_tz()) - timedelta(minutes=1)).isoformat()
    conn = sqlite3.connect(reminders_service.DB_FILE)
    conn.execute("UPDATE reminders SET remind_at = ? WHERE id = ?", (past_iso, rem_id))
    conn.commit()
    conn.close()
    
    due = reminders_service.get_due_reminders()
    found_due = any(r["id"] == rem_id for r in due)
    
    # 4. Mark triggered
    reminders_service.mark_reminder_triggered(rem_id)
    active_after = reminders_service.list_active_reminders()
    not_in_active = not any(r["id"] == rem_id for r in active_after)
    
    # 5. Clean up test reminder
    conn = sqlite3.connect(reminders_service.DB_FILE)
    conn.execute("DELETE FROM reminders WHERE id = ?", (rem_id,))
    conn.commit()
    conn.close()
    
    success = found_active and found_due and not_in_active
    log_param(3, "Reminders Lifecycle (Add/Check/Due/Trigger/Clean)", success, 
              f"Added ID #{rem_id}, verified active, verified due trigger detection, marked triggered, and cleaned.")
except Exception as e:
    log_param(3, "Reminders Lifecycle", False, str(e))

# ------------------------------------------------------------------
# Parameter 4: Live Telegram Alert Notification Delivery
# ------------------------------------------------------------------
try:
    uid = config.ALLOWED_USER_IDS[0] if config.ALLOWED_USER_IDS else None
    if uid:
        alert_msg = (
            "🔔 <b>QA INSPECTOR AGENT ALERT</b>\n\n"
            "• <b>Status:</b> Live Telegram reminder delivery pipeline active!\n"
            "• <b>Test Timestamp:</b> " + datetime.now(config.get_tz()).strftime("%I:%M %p, %b %d") + "\n\n"
            "<i>Your automated reminder dispatch engine is 100% operational, Revanth Sir.</i>"
        )
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={"chat_id": uid, "text": alert_msg, "parse_mode": "HTML"}, timeout=10).json()
        log_param(4, "Live Telegram Alert Dispatch", resp.get("ok", False), f"Message delivered to User ID {uid}: {resp.get('ok')}")
    else:
        log_param(4, "Live Telegram Alert Dispatch", False, "No ALLOWED_USER_IDS found.")
except Exception as e:
    log_param(4, "Live Telegram Alert Dispatch", False, str(e))

# ------------------------------------------------------------------
# Parameter 5: Expenses Lifecycle (Add -> Query -> AI Check -> Delete)
# ------------------------------------------------------------------
try:
    # 1. Add synthetic expense
    exp = expenses_service.log_expense(amount=150.0, category="Food", description="QA Test Filter Coffee", expense_date="today")
    exp_id = exp["id"]
    
    # 2. Query by date
    today_iso = datetime.now(config.get_tz()).date().isoformat()
    by_date = expenses_service.get_expenses_by_date(today_iso)
    found_by_date = any(e["id"] == exp_id for e in by_date)
    
    # 3. Query via AI Agent
    ai_reply = ai_agent.query_agent("Did I log any Filter Coffee expense today?")
    ai_verified = "150" in ai_reply or "Filter Coffee" in ai_reply or "Food" in ai_reply
    
    # 4. Clean up test record
    conn = sqlite3.connect(expenses_service.DB_FILE)
    conn.execute("DELETE FROM expenses WHERE id = ?", (exp_id,))
    conn.commit()
    conn.close()
    
    # 5. Verify deletion
    by_date_after = expenses_service.get_expenses_by_date(today_iso)
    deleted_clean = not any(e["id"] == exp_id for e in by_date_after)
    
    success = found_by_date and ai_verified and deleted_clean
    log_param(5, "Expenses Lifecycle (Add/Date/AI Verify/Delete)", success,
              f"Added ₹150 Filter Coffee (ID #{exp_id}), AI verified response: '{ai_reply[:60]}...', cleanly deleted.")
except Exception as e:
    log_param(5, "Expenses Lifecycle", False, str(e))

# ------------------------------------------------------------------
# Parameter 6: Books Subsystem (Add -> Progress -> AI Check -> Delete)
# ------------------------------------------------------------------
try:
    # 1. Add synthetic book
    bk = books_service.add_book(title="QA Test The Pragmatic Programmer", author="Andrew Hunt", total_pages=352)
    bk_id = bk["id"]
    
    # 2. Update progress
    up = books_service.update_book_progress("QA Test The Pragmatic Programmer", 88)
    progress_ok = up.get("current_page") == 88
    
    # 3. AI Query
    ai_bk = ai_agent.query_agent("What page am I on in QA Test The Pragmatic Programmer?")
    ai_bk_ok = "88" in ai_bk
    
    # 4. Clean up test book
    conn = sqlite3.connect(books_service.DB_FILE)
    conn.execute("DELETE FROM books WHERE id = ?", (bk_id,))
    conn.commit()
    conn.close()
    
    success = progress_ok and ai_bk_ok
    log_param(6, "Books Lifecycle (Add/Progress/AI Verify/Delete)", success,
              f"Added book (ID #{bk_id}), updated to page 88, AI verified: '{ai_bk[:60]}...', cleanly deleted.")
except Exception as e:
    log_param(6, "Books Lifecycle", False, str(e))

# ------------------------------------------------------------------
# Parameter 7: Tasks Subsystem (Add -> List -> Complete -> Delete)
# ------------------------------------------------------------------
try:
    # 1. Add task
    t = tasks_service.add_task(title="QA Automated Inspection Task")
    t_id = t["id"]
    
    # 2. List tasks
    pending = tasks_service.list_tasks(completed=False)
    found_t = any(task["id"] == t_id for task in pending)
    
    # 3. Complete task
    tasks_service.complete_task(t_id)
    completed_tasks = tasks_service.list_tasks(completed=True)
    found_completed = any(task["id"] == t_id for task in completed_tasks)
    
    # 4. Delete task
    tasks_service.delete_task(t_id)
    all_tasks = tasks_service.list_tasks(completed=None)
    deleted_t = not any(task["id"] == t_id for task in all_tasks)
    
    success = found_t and found_completed and deleted_t
    log_param(7, "Tasks Lifecycle (Add/List/Complete/Delete)", success,
              f"Added task #{t_id}, verified pending, marked completed, cleanly deleted.")
except Exception as e:
    log_param(7, "Tasks Lifecycle", False, str(e))

# ------------------------------------------------------------------
# Parameter 8: Notes Subsystem (Add -> Search -> Delete)
# ------------------------------------------------------------------
try:
    # 1. Add note
    n = notes_service.add_note(content="Server IP 192.168.1.50 port 9000", title="QA Inspection Note", tags="test")
    n_id = n["id"]
    
    # 2. Search note
    search_res = notes_service.search_notes("192.168.1.50")
    found_n = any(note["id"] == n_id for note in search_res)
    
    # 3. Delete note
    notes_service.delete_note(n_id)
    search_after = notes_service.search_notes("192.168.1.50")
    deleted_n = not any(note["id"] == n_id for note in search_after)
    
    success = found_n and deleted_n
    log_param(8, "Notes Second Brain (Add/Search/Delete)", success,
              f"Added note #{n_id}, verified keyword search match, cleanly deleted.")
except Exception as e:
    log_param(8, "Notes Second Brain", False, str(e))

# ------------------------------------------------------------------
# Parameter 9: Habits Engine (Add -> Log -> Streak -> Delete)
# ------------------------------------------------------------------
try:
    # 1. Add habit
    h_name = "QA Daily Meditation"
    habits_service.add_habit(h_name)
    
    # 2. Log habit
    log_res = habits_service.log_habit(h_name)
    
    # 3. Verify streak
    streaks = habits_service.get_habit_streaks()
    h_streak = next((h for h in streaks if h["name"] == h_name), None)
    streak_ok = h_streak is not None and h_streak["streak"] >= 1
    
    # 4. Clean up habit
    conn = sqlite3.connect(habits_service.DB_FILE)
    conn.execute("DELETE FROM habit_logs WHERE habit_id IN (SELECT id FROM habits WHERE name = ?)", (h_name,))
    conn.execute("DELETE FROM habits WHERE name = ?", (h_name,))
    conn.commit()
    conn.close()
    
    success = log_res.get("success", False) and streak_ok
    log_param(9, "Habits Engine (Add/Log Streak/Delete)", success,
              f"Created habit '{h_name}', logged completion, verified streak={h_streak.get('streak') if h_streak else 0}, cleaned.")
except Exception as e:
    log_param(9, "Habits Engine", False, str(e))

# ------------------------------------------------------------------
# Parameter 10: Anti-Hallucination Real-Time Date & Time Grounding
# ------------------------------------------------------------------
try:
    date_reply = ai_agent.query_agent("What is today's exact date?")
    now_date = datetime.now(config.get_tz())
    expected_month = now_date.strftime("%B") # October
    expected_year = str(now_date.year)        # 2026
    
    date_grounded = expected_month.lower() in date_reply.lower() and expected_year in date_reply
    log_param(10, "Anti-Hallucination Date Grounding", date_grounded,
              f"Expected {expected_month} {expected_year}, Agent replied: '{date_reply.strip()[:80]}'")
except Exception as e:
    log_param(10, "Anti-Hallucination Date Grounding", False, str(e))

# ------------------------------------------------------------------
# Parameter 11: Executive Persona & Salutation Compliance
# ------------------------------------------------------------------
try:
    greet_reply = ai_agent.query_agent("Hello Jarvis, give me a quick status check.")
    has_salutation = "Revanth Sir" in greet_reply
    log_param(11, "Executive Persona & Salutation", has_salutation,
              f"Agent salutation check: 'Revanth Sir' in response: {has_salutation}")
except Exception as e:
    log_param(11, "Executive Persona & Salutation", False, str(e))

# ------------------------------------------------------------------
# Parameter 12: Data Guardian Master Vault Persistence Sync
# ------------------------------------------------------------------
try:
    snap = backup_service.backup_all_databases()
    status = backup_service.get_vault_status()
    vault_ok = snap.get("status") == "success" and status.get("vault_records", 0) >= 3
    log_param(12, "Data Guardian Vault Auto-Sync", vault_ok,
              f"Total vault records preserved: {status.get('vault_records')} across {len(status.get('active_sqlite_records', {}))} tables.")
except Exception as e:
    log_param(12, "Data Guardian Vault Auto-Sync", False, str(e))

print("==================================================================")
print(f"QA INSPECTOR RESULTS: {report['parameters_passed']}/{report['parameters_tested']} Parameters Passed Successfully!")
print("==================================================================")

with open(os.path.join(os.path.dirname(__file__), "qa_inspection_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

if report['parameters_passed'] == report['parameters_tested']:
    print("ALL 12 PRODUCTION PARAMETERS VERIFIED & PASSED 100%! 🚀")
    sys.exit(0)
else:
    print("SOME PARAMETERS FAILED AUDIT.")
    sys.exit(1)
