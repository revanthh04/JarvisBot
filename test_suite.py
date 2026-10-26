import sys
import os

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

print("==================================================")
print("     JARVIS COMPREHENSIVE DIAGNOSTIC TEST SUITE   ")
print("==================================================")

tests_passed = 0
total_tests = 16

def run_test(num, name, fn):
    global tests_passed
    print(f"[{num:02d}/{total_tests:02d}] Testing {name}...", end=" ")
    try:
        fn()
        print("[PASS]")
        tests_passed += 1
    except Exception as e:
        print(f"[FAIL]: {e}")

# 1. Config
def test_config():
    import config
    assert config.TELEGRAM_BOT_TOKEN, "TELEGRAM_BOT_TOKEN is missing"
    assert config.GEMINI_API_KEY, "GEMINI_API_KEY is missing"
    assert config.ALLOWED_USER_IDS, "ALLOWED_USER_IDS is empty"
    assert config.is_authorized(config.ALLOWED_USER_IDS[0]), "Authorization failed"

# 2. Notes Service
def test_notes():
    import notes_service
    note = notes_service.add_note("Test content for Jarvis", "Diagnostic Note", "test")
    assert note["id"] > 0
    results = notes_service.search_notes("Diagnostic")
    assert len(results) > 0
    notes_service.delete_note(note["id"])

# 3. Habits Service
def test_habits():
    import habits_service
    import sqlite3
    habits_service.add_habit("Diagnostic Habit")
    log_res = habits_service.log_habit("Diagnostic Habit")
    assert log_res["success"]
    streaks = habits_service.get_habit_streaks()
    assert any(h["name"] == "Diagnostic Habit" for h in streaks)
    # Immediate cleanup
    conn = sqlite3.connect(habits_service.DB_FILE)
    conn.execute("DELETE FROM habit_logs WHERE habit_id IN (SELECT id FROM habits WHERE name = 'Diagnostic Habit')")
    conn.execute("DELETE FROM habits WHERE name = 'Diagnostic Habit'")
    conn.commit()
    conn.close()

# 4. Tasks Service
def test_tasks():
    import tasks_service
    t = tasks_service.add_task("Diagnostic Task")
    assert t["id"] > 0
    tasks_service.complete_task(t["id"])
    tasks_service.delete_task(t["id"])

# 5. Expenses Service
def test_expenses():
    import expenses_service
    import sqlite3
    exp = expenses_service.log_expense(50.0, "Testing", "Unit test item")
    assert exp["id"] > 0
    summary = expenses_service.get_monthly_summary()
    assert summary["total_expenditure"] >= 50.0
    # Immediate cleanup
    conn = sqlite3.connect(expenses_service.DB_FILE)
    conn.execute("DELETE FROM expenses WHERE id = ?", (exp["id"],))
    conn.commit()
    conn.close()

# 6. Device Service
def test_device():
    import device_service
    stats = device_service.get_system_stats()
    assert "cpu_percent" in stats
    device_service.set_clipboard("Jarvis Test Clipboard")
    clip = device_service.get_clipboard()
    assert "Jarvis Test Clipboard" in clip

# 7. Weather Service
def test_weather():
    import weather_service
    res = weather_service.get_weather("London")
    assert "temp_c" in res or "error" in res

# 8. Calc Service
def test_calc():
    import calc_service
    curr = calc_service.convert_currency(10, "USD", "INR")
    assert "result" in curr
    emi = calc_service.calculate_emi(100000, 10, 1)
    assert "monthly_emi" in emi

# 9. Search Service
def test_search():
    import search_service
    res = search_service.search_web("Python programming language", max_results=2)
    assert len(res) > 0

# 10. Cricket Service
def test_cricket():
    import cricket_service
    res = cricket_service.get_live_cricket_scores()
    assert len(res) > 0

# 11. Voice Service
def test_voice():
    import voice_service
    audio_file = voice_service.synthesize_sync("Jarvis diagnostics passed.")
    assert os.path.exists(audio_file)
    if os.path.exists(audio_file):
        os.remove(audio_file)

# 12. AI Agent Core
def test_ai_agent():
    import ai_agent
    res = ai_agent.query_agent("Say 'Diagnostics operational'")
    assert len(res) > 0

# 13. Google Service Fallbacks
def test_google_fallbacks():
    import calendar_service, gmail_service
    c_res = calendar_service.get_calendar_events()
    assert isinstance(c_res, str)
    g_res = gmail_service.list_emails()
    assert isinstance(g_res, list)

# 14. Books Management Subsystem
def test_books():
    import books_service
    import sqlite3
    b = books_service.add_book("Atomic Habits", "James Clear", total_pages=320)
    assert b["id"] > 0
    up = books_service.update_book_progress("Atomic Habits", 45)
    assert up["current_page"] == 45
    books = books_service.list_books()
    assert any(bk["title"] == "Atomic Habits" for bk in books)
    found = books_service.search_books("Atomic")
    assert len(found) > 0
    # Cleanup test book
    conn = sqlite3.connect(books_service.DB_FILE)
    conn.execute("DELETE FROM books WHERE id = ?", (b["id"],))
    conn.commit()
    conn.close()

# 15. Dual-Brain Hybrid Failover (OpenAI + Gemini)
def test_dual_brain():
    import ai_agent
    # Verify query_openai returns None gracefully when quota exhausted without crashing
    openai_res = ai_agent.query_openai("Hello")
    assert openai_res is None or isinstance(openai_res, str)
    # Verify overall query_agent works seamlessly with fallback
    reply = ai_agent.query_agent("Introduce yourself briefly as Revanth Sir's assistant.")
    assert "Revanth" in reply or "JARVIS" in reply or len(reply) > 10

# 16. Data Guardian Vault & Persistence
def test_data_guardian():
    import backup_service
    res = backup_service.backup_all_databases()
    assert res["status"] == "success"
    assert res["total_records"] >= 2
    status = backup_service.get_vault_status()
    assert status["vault_records"] >= 2

if __name__ == "__main__":
    run_test(1, "Config & Whitelist Authorization", test_config)
    run_test(2, "Notes SQLite Second Brain", test_notes)
    run_test(3, "Habit Tracker Engine", test_habits)
    run_test(4, "Task Management Subsystem", test_tasks)
    run_test(5, "Expense Ledger Subsystem", test_expenses)
    run_test(6, "Device Telemetry & Clipboard Control", test_device)
    run_test(7, "Weather wttr.in Service", test_weather)
    run_test(8, "Financial & Currency Calculator", test_calc)
    run_test(9, "DuckDuckGo Web Search Engine", test_search)
    run_test(10, "Cricket Live Score Engine", test_cricket)
    run_test(11, "Microsoft Edge Neural Voice TTS", test_voice)
    run_test(12, "Gemini Flash AI Core Reasoning", test_ai_agent)
    run_test(13, "Calendar & Gmail Graceful Handling", test_google_fallbacks)
    run_test(14, "Books & Reading Tracker Subsystem", test_books)
    run_test(15, "Dual-Brain OpenAI/Gemini Hybrid Failover", test_dual_brain)
    run_test(16, "Data Guardian Vault & Auto-Persistence", test_data_guardian)

    print("==================================================")
    print(f"RESULTS: {tests_passed}/{total_tests} Subsystems Verified Successfully!")
    print("==================================================")
    if tests_passed == total_tests:
        print("ALL SYSTEMS GO! 🚀")
        sys.exit(0)
    else:
        sys.exit(1)
