"""Offline regressions. Import only source copies in a temporary workspace.

No production database, credential file, clipboard or remote account is used.
"""
import atexit
import asyncio
import base64
from contextlib import ExitStack, closing
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = tempfile.TemporaryDirectory(prefix="jarvis-regressions-")
atexit.register(SANDBOX.cleanup)
for source in ROOT.glob("*.py"):
    shutil.copy2(source, Path(SANDBOX.name) / source.name)
sys.path.insert(0, SANDBOX.name)
ENV = patch.dict(os.environ, {
    "JARVIS_DATA_DIR": SANDBOX.name,
    "GOOGLE_TOKEN_JSON": "", "GOOGLE_SPREADSHEET_ID": "", "OPENAI_API_KEY": "",
    "GEMINI_API_KEY": "offline-test-key", "TELEGRAM_BOT_TOKEN": "123:test",
    "ALLOWED_USER_IDS": "", "OPEN_ACCESS": "false", "USER_TIMEZONE": "Asia/Kolkata",
    "SHEETS_DURABLE_STORAGE": "false",
})
ENV.start()
atexit.register(ENV.stop)
with patch("dotenv.load_dotenv"):
    import config
import backup_service
import sheets_service
SERVICES = {name: importlib.import_module(f"{name}_service")
            for name in ("notes", "tasks", "habits", "expenses", "books", "reminders")}
import ai_agent
import bot

OTHER = 123456789
THIRD = 987654321


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(sheets_service, "trigger_background_sync"))
        # A mistaken live call fails the test instead of contacting an account.
        for target in ("requests.sessions.Session.request", "httpx.Client.send",
                       "httplib2.Http.request"):
            self.stack.enter_context(patch(target, side_effect=AssertionError("Network disabled in tests")))
        config.set_current_user(config.ADMIN_USER_ID, "Revanth Sir")
        bot.gmail_service._drafts.clear()
        config.MISSING_DATABASES.clear()
        self.stack.enter_context(patch.object(config, "OPEN_ACCESS", False))
        self.stack.enter_context(patch.object(config, "ALLOWED_USER_IDS", [OTHER, THIRD]))
        for service in SERVICES.values():
            service.init_db()
            with closing(sqlite3.connect(service.DB_FILE)) as conn:
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'").fetchall()
                for (table,) in tables:
                    conn.execute(f'DELETE FROM "{table}"')
                conn.commit()
        Path(backup_service.VAULT_FILE).unlink(missing_ok=True)

    def freeze_reminders(self, hour=11, minute=0):
        clock = self.stack.enter_context(patch.object(SERVICES["reminders"], "datetime", wraps=datetime))
        clock.now.return_value = config.get_tz().localize(datetime(2026, 11, 3, hour, minute))
        return clock.now.return_value


class AccessTests(IsolatedTest):
    def test_guarded_tools_keep_valid_gemini_function_schemas(self):
        for fn in ai_agent.tools_list:
            with self.subTest(tool=fn.__name__):
                declaration = ai_agent.types.FunctionDeclaration.from_callable(
                    client=SimpleNamespace(vertexai=False), callable=fn,
                )
                self.assertEqual(declaration.name, fn.__name__)

    def test_tool_identity_cannot_override_admin_either(self):
        self.assertEqual(config.resolve_user_id(OTHER), config.ADMIN_USER_ID)

    def test_empty_allowlist_denies_strangers(self):
        config.ALLOWED_USER_IDS = []
        self.assertFalse(config.is_authorized(OTHER))
        self.assertTrue(config.is_authorized(config.ADMIN_USER_ID))
        config.OPEN_ACCESS = True
        self.assertTrue(config.is_authorized(OTHER))

    def test_cannot_read_or_delete_another_users_note(self):
        note = SERVICES["notes"].add_note("private content", "Private")
        config.set_current_user(OTHER)
        self.assertEqual(SERVICES["notes"].list_notes(user_id=config.ADMIN_USER_ID), [])
        SERVICES["notes"].delete_note(note["id"], user_id=config.ADMIN_USER_ID)
        config.set_current_user(config.ADMIN_USER_ID)
        self.assertEqual(len(SERVICES["notes"].list_notes()), 1)

    def test_private_services_reject_non_admin_before_io(self):
        config.set_current_user(OTHER)
        calls = [
            (bot.gmail_service.list_emails, ()), (bot.gmail_service.read_email, ("id",)),
            (bot.gmail_service.send_email, ("nobody@example.invalid", "subject", "body")),
            (bot.calendar_service.get_calendar_events, ()),
            (bot.calendar_service.add_calendar_event, ("Meeting", "2026-11-04 10:00")),
            (bot.device_service.get_clipboard, ()), (bot.device_service.set_clipboard, ("test",)),
            (bot.device_service.lock_workstation, ()), (bot.device_service.set_volume, ("up",)),
            (bot.device_service.take_screenshot, ()),
            (bot.linkedin_service.get_linkedin_profile, ()), (bot.linkedin_service.post_to_linkedin, ("test",)),
            (sheets_service.get_sheets_link, ()), (sheets_service.sync_google_sheets, ()),
        ]
        for fn, args in calls:
            with self.subTest(fn=fn.__name__), self.assertRaises(PermissionError):
                fn(*args)

    def test_non_admin_tool_catalog_excludes_private_services(self):
        config.set_current_user(OTHER)
        modules = {fn.__module__ for fn in ai_agent.get_available_tools()}
        self.assertFalse(modules & {"gmail_service", "calendar_service", "device_service", "sheets_service", "linkedin_service"})
        self.assertIn("notes_service", modules)

    def test_restricted_handler_restores_identity_after_failure(self):
        @bot.restricted
        async def failing(update, context):
            self.assertEqual(config.get_current_user_id(), OTHER)
            raise RuntimeError("handler failed")
        update = SimpleNamespace(effective_user=SimpleNamespace(id=OTHER, first_name="Guest"))
        async def run():
            with self.assertRaises(RuntimeError):
                await failing(update, None)
            self.assertEqual(config.get_current_user_id(), config.ADMIN_USER_ID)
        asyncio.run(run())

    def test_private_commands_deny_guest(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=OTHER, first_name="Guest"),
                                 message=SimpleNamespace(reply_text=AsyncMock()))
        for name in ("cmd_agenda", "cmd_emails", "cmd_linkedin", "cmd_sheets", "cmd_syncsheets"):
            asyncio.run(getattr(bot, name)(update, SimpleNamespace(args=[])))
        self.assertEqual(update.message.reply_text.await_count, 5)


class ReminderTests(IsolatedTest):
    def test_relative_wording_preserves_message_and_delay(self):
        now = self.freeze_reminders()
        for phrase, minutes in (("after 2 mins", 2), ("with in 5 mins", 5), ("within 5 mins", 5), ("in 2 mins", 2)):
            with self.subTest(phrase=phrase):
                result = SERVICES["reminders"].create_reminder("remind me to drink water " + phrase)
                self.assertEqual(result["message"], "Drink water")
                row = next(r for r in SERVICES["reminders"].list_active_reminders() if r["id"] == result["id"])
                self.assertEqual((datetime.fromisoformat(row["raw_remind_at"]) - now).total_seconds(), minutes * 60)

    def test_startup_does_not_replay_snapshot_reminders(self):
        now = self.freeze_reminders()
        service = SERVICES["reminders"]
        old = service.create_reminder("Old alert", delay_minutes=1)
        recurring = service.create_reminder("Water every 20 mins")
        future = service.create_reminder("Future appointment", delay_minutes=60)
        with closing(sqlite3.connect(service.DB_FILE)) as conn:
            conn.execute("UPDATE reminders SET remind_at = '2026-10-23T13:20:00+05:30' WHERE id IN (?, ?)", (old["id"], recurring["id"]))
            conn.commit()
        self.assertEqual(service.reconcile_overdue_at_startup(), {"expired": 1, "rescheduled": 1})
        self.assertEqual(service.get_due_reminders(), [])
        active = {r["id"] for r in service.list_active_reminders()}
        self.assertEqual(active, {future["id"], recurring["id"]})
        self.assertEqual(service.reconcile_overdue_at_startup(), {"expired": 0, "rescheduled": 0})

    def test_compact_am_remains_morning(self):
        self.freeze_reminders(5)
        SERVICES["reminders"].create_reminder("Call", time_str="6:30am")
        raw = SERVICES["reminders"].list_active_reminders()[0]["raw_remind_at"]
        self.assertEqual(datetime.fromisoformat(raw).hour, 6)

    def test_compact_hour_and_tomorrow(self):
        self.freeze_reminders(11)
        SERVICES["reminders"].create_reminder("Call tomorrow at 6pm")
        raw = SERVICES["reminders"].list_active_reminders()[0]["raw_remind_at"]
        self.assertEqual(datetime.fromisoformat(raw).isoformat(), "2026-11-04T18:00:00+05:30")

    def test_invalid_or_missing_time_never_creates_guessed_reminder(self):
        self.freeze_reminders()
        for kwargs in ({"time_str": "25:99"}, {"time_str": "2020-01-01 10:00"},
                       {"delay_minutes": -5}, {}, {"is_recurring": True, "repeat_interval_minutes": 0}):
            with self.subTest(kwargs=kwargs):
                result = SERVICES["reminders"].create_reminder("Call", **kwargs)
                self.assertNotIn("id", result)
        self.assertEqual(SERVICES["reminders"].list_active_reminders(), [])

    def test_recurring_schedule_is_saved_to_vault(self):
        self.freeze_reminders()
        rem = SERVICES["reminders"].create_reminder("Drink water every 20 mins")
        SERVICES["reminders"].reschedule_recurring_reminder(rem["id"], 30)
        vault = json.loads(Path(backup_service.VAULT_FILE).read_text(encoding="utf-8"))
        self.assertIn("11:30:00", vault["tables"]["reminders"][0]["remind_at"])

    def test_failed_delivery_preserves_due_reminder(self):
        rem = {"id": 1, "user_id": OTHER, "message": "Budget < 50 & lunch", "is_recurring": False}
        with patch.object(SERVICES["reminders"], "get_due_reminders", return_value=[rem]), \
             patch.object(SERVICES["reminders"], "mark_reminder_triggered") as mark:
            ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("offline"))))
            asyncio.run(bot.check_reminders_job(ctx))
            mark.assert_not_called()
            self.assertIn("Budget &lt; 50 &amp; lunch", ctx.bot.send_message.call_args.kwargs["text"])

    def test_recurring_delivery_only_advances_after_success(self):
        rem = {"id": 1, "user_id": OTHER, "message": "Water", "is_recurring": True, "repeat_interval_minutes": 20}
        with patch.object(SERVICES["reminders"], "get_due_reminders", return_value=[rem]), \
             patch.object(SERVICES["reminders"], "reschedule_recurring_reminder") as advance:
            ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("offline"))))
            asyncio.run(bot.check_reminders_job(ctx))
            advance.assert_not_called()
            ctx.bot.send_message.side_effect = None
            asyncio.run(bot.check_reminders_job(ctx))
            advance.assert_called_once_with(1, 20)


class BackupTests(IsolatedTest):
    def test_habit_history_survives_recovery(self):
        SERVICES["habits"].log_habit("Walk", "2026-11-03")
        backup_service.backup_all_databases()
        Path(SERVICES["habits"].DB_FILE).unlink()
        config.MISSING_DATABASES.add("habits")
        result = backup_service.restore_all_databases()
        self.assertEqual(result["status"], "restored")
        with closing(sqlite3.connect(SERVICES["habits"].DB_FILE)) as conn:
            self.assertEqual(conn.execute("SELECT log_date FROM habit_logs").fetchall(), [("2026-11-03",)])

    def test_stale_vault_does_not_resurrect_deleted_records(self):
        SERVICES["notes"].add_note("delete me", "Old")
        with closing(sqlite3.connect(SERVICES["notes"].DB_FILE)) as conn:
            conn.execute("DELETE FROM notes")
            conn.commit()
        backup_service.restore_all_databases()
        self.assertEqual(SERVICES["notes"].list_notes(), [])

    def test_failed_backup_preserves_previous_file(self):
        SERVICES["notes"].add_note("Keep me", "Saved")
        before = Path(backup_service.VAULT_FILE).read_bytes()
        with patch.object(backup_service.sqlite3, "connect", side_effect=sqlite3.OperationalError("locked")):
            self.assertEqual(backup_service.backup_all_databases()["status"], "error")
        self.assertEqual(Path(backup_service.VAULT_FILE).read_bytes(), before)

    def test_failed_atomic_replace_preserves_previous_file(self):
        backup_service.backup_all_databases()
        before = Path(backup_service.VAULT_FILE).read_bytes()
        with patch.object(backup_service.os, "replace", side_effect=OSError("disk full")):
            self.assertEqual(backup_service.backup_all_databases()["status"], "error")
        self.assertEqual(Path(backup_service.VAULT_FILE).read_bytes(), before)
        self.assertEqual(list(Path(SANDBOX.name).glob("vault-*.tmp")), [])

    def test_due_reminder_is_not_retired_during_restore(self):
        self.freeze_reminders()
        SERVICES["reminders"].create_reminder("Call", delay_minutes=5)
        Path(SERVICES["reminders"].DB_FILE).unlink()
        config.MISSING_DATABASES.add("reminders")
        with patch.object(backup_service, "datetime", wraps=datetime) as clock:
            clock.now.return_value = config.get_tz().localize(datetime(2026, 11, 4))
            backup_service.restore_all_databases()
        self.assertEqual(len(SERVICES["reminders"].list_active_reminders()), 1)


class RoutingAndJobsTests(IsolatedTest):
    def test_code_formatting_does_not_leak_internal_placeholders(self):
        result = bot.markdown_to_telegram_html("Notice: `jarvis-bot` exceeded memory.\n```\na < b\n```")
        self.assertIn("<code>jarvis-bot</code>", result)
        self.assertIn("a &lt; b", result)
        self.assertNotIn("INLINECODE", result)
        self.assertNotIn("CODEBLOCK", result)

    def test_direct_reminder_saved_without_model(self):
        self.freeze_reminders()
        with patch.object(ai_agent, "query_gemini_agent") as model:
            self.assertIn("Reminder set", ai_agent.query_agent('"Remind me in 1 minute to drink water"'))
            model.assert_not_called()
        self.assertEqual(len(SERVICES["reminders"].list_active_reminders()), 1)

    def test_date_typo_uses_clock(self):
        with patch.object(ai_agent, "datetime", wraps=datetime) as clock:
            clock.now.return_value = config.get_tz().localize(datetime(2026, 10, 23))
            self.assertIn("October 23, 2026", ai_agent.query_agent("what is data of today ?"))

    def test_expense_total_includes_more_than_fifty_rows(self):
        with closing(sqlite3.connect(SERVICES["expenses"].DB_FILE)) as conn:
            conn.executemany("INSERT INTO expenses (user_id, amount, category, description, expense_date) VALUES (?, 10, 'Food', 'Lunch', '2026-10-22')", [(config.ADMIN_USER_ID,)] * 60)
            conn.commit()
        result = SERVICES["expenses"].search_expenses(category="Food")
        self.assertEqual(result["count"], 60)
        self.assertEqual(result["total_amount"], 600)
        self.assertEqual(len(result["entries"]), 50)
        self.assertIn("₹600.00", ai_agent.query_agent("expenses on food ?"))

    def test_personal_memory_and_followups_use_tools(self):
        with patch.object(ai_agent, "openai_client", Mock()), \
             patch.object(ai_agent, "query_openai", return_value="unguarded") as chat, \
             patch.object(ai_agent, "query_gemini_agent", return_value="grounded"):
            for prompt in ("Remember my locker number is 17", "What did I save?", "Yes, do that", "What do I have tomorrow?"):
                self.assertEqual(ai_agent.query_agent(prompt), "grounded")
            chat.assert_not_called()

    def test_voice_transcript_reaches_tool_router(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=OTHER, first_name="Guest"),
                                 effective_chat=SimpleNamespace(id=OTHER),
                                 message=SimpleNamespace(voice=SimpleNamespace(file_id="voice"), audio=None,
                                                         reply_voice=AsyncMock(), reply_text=AsyncMock()))
        ctx = SimpleNamespace(bot=SimpleNamespace(send_chat_action=AsyncMock(),
                              get_file=AsyncMock(return_value=SimpleNamespace(download_to_memory=AsyncMock()))))
        audio = Path(SANDBOX.name) / "reply.ogg"
        audio.write_bytes(b"offline test")
        def reply(transcript):
            self.assertEqual(config.get_current_user_id(), OTHER)
            return "Saved"
        with patch.object(ai_agent, "transcribe_audio", return_value="Remember this") as transcribe, \
             patch.object(ai_agent, "query_agent", side_effect=reply) as query, \
             patch.object(bot.voice_service, "text_to_speech", new=AsyncMock(return_value=str(audio))):
            asyncio.run(bot.handle_voice(update, ctx))
            transcribe.assert_called_once()
            query.assert_called_once_with("Remember this")
            update.message.reply_voice.assert_awaited_once()

    def test_evening_checkins_use_recipient_habits(self):
        SERVICES["habits"].add_habit("Private admin habit")
        with config.user_context(OTHER):
            SERVICES["habits"].add_habit("Guest walk")
        ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        asyncio.run(bot.scheduled_evening_habits(ctx))
        messages = {call.kwargs["chat_id"]: call.kwargs["text"] for call in ctx.bot.send_message.call_args_list}
        self.assertIn("Guest walk", messages[OTHER])
        self.assertNotIn(THIRD, messages)
        self.assertTrue(all("Private admin habit" not in msg for msg in messages.values()))

    def test_briefing_queries_in_recipient_context(self):
        seen = []
        def reply(prompt):
            seen.append(config.get_current_user_id())
            return "Briefing"
        ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        with patch.object(ai_agent, "query_agent", side_effect=reply), \
             patch.object(bot.weather_service, "get_weather", return_value={}), \
             patch.object(SERVICES["tasks"], "list_tasks", side_effect=lambda **kw: seen.append(config.get_current_user_id()) or []):
            asyncio.run(bot.send_briefing_to_user(ctx, OTHER))
        self.assertEqual(seen, [OTHER, OTHER])

    def test_habits_and_monthly_totals_use_configured_timezone(self):
        local_time = config.get_tz().localize(datetime(2026, 12, 1, 1))
        for name in ("habits", "expenses"):
            clock = self.stack.enter_context(patch.object(SERVICES[name], "datetime", wraps=datetime))
            clock.now.return_value = local_time
        SERVICES["habits"].log_habit("Walk")
        self.assertTrue(SERVICES["habits"].list_habits()[0]["completed_today"])
        SERVICES["expenses"].log_expense(50, expense_date="2026-12-01")
        self.assertEqual(SERVICES["expenses"].get_monthly_summary()["total_expenditure"], 50)
        with closing(sqlite3.connect(SERVICES["habits"].DB_FILE)) as conn:
            self.assertEqual(conn.execute("SELECT log_date FROM habit_logs").fetchone()[0], "2026-12-01")


class SheetsTests(IsolatedTest):
    def test_successful_sync_writes_before_trimming_stale_rows(self):
        service = Mock()
        values = service.spreadsheets.return_value.values.return_value
        operations = []
        values.batchUpdate.return_value.execute.side_effect = lambda: operations.append("write")
        values.clear.return_value.execute.side_effect = lambda: operations.append("clear")
        with patch.object(sheets_service, "get_sheets_service", return_value=(service, "ok")), \
             patch.object(sheets_service, "ensure_spreadsheet", return_value=("test-sheet", None)), \
             patch.object(sheets_service, "extract_table_data", return_value=[[1, "Text"]]):
            result = sheets_service.sync_all_to_sheets()
        self.assertEqual(result["status"], "success")
        self.assertEqual(operations, ["write"] + ["clear"] * 5)
        self.assertTrue(all("!A3:Z" in call.kwargs["range"] for call in values.clear.call_args_list))

    def test_export_only_includes_admin_records(self):
        SERVICES["notes"].add_note("Admin", "Admin note")
        with config.user_context(OTHER):
            SERVICES["notes"].add_note("Guest", "Guest note")
        rows = sheets_service.extract_table_data("Notes")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "Admin note")

    def test_source_read_failure_does_not_clear_sheet(self):
        service = Mock()
        with patch.object(sheets_service, "get_sheets_service", return_value=(service, "ok")), \
             patch.object(sheets_service, "ensure_spreadsheet", return_value=("test-sheet", None)), \
             patch.object(sheets_service, "extract_table_data", side_effect=sqlite3.OperationalError("unreadable")):
            self.assertEqual(sheets_service.sync_all_to_sheets()["status"], "error")
        service.spreadsheets.return_value.values.return_value.clear.assert_not_called()

    def test_sheet_write_failure_does_not_clear_existing_rows(self):
        service = Mock()
        values = service.spreadsheets.return_value.values.return_value
        values.batchUpdate.return_value.execute.side_effect = RuntimeError("write failed")
        with patch.object(sheets_service, "get_sheets_service", return_value=(service, "ok")), \
             patch.object(sheets_service, "ensure_spreadsheet", return_value=("test-sheet", None)), \
             patch.object(sheets_service, "extract_table_data", return_value=[[1, "=not a formula"]]):
            self.assertEqual(sheets_service.sync_all_to_sheets()["status"], "error")
        values.clear.assert_not_called()
        self.assertEqual(values.batchUpdate.call_args.kwargs["body"]["valueInputOption"], "RAW")

    def test_inaccessible_configured_sheet_does_not_create_duplicate(self):
        service = Mock()
        service.spreadsheets.return_value.get.return_value.execute.side_effect = RuntimeError("temporary outage")
        with patch.object(sheets_service, "get_spreadsheet_id", return_value="existing"):
            sid, error = sheets_service.ensure_spreadsheet(service)
        self.assertIsNone(sid)
        self.assertIn("inaccessible", error)
        service.spreadsheets.return_value.create.assert_not_called()


class GoogleTests(IsolatedTest):
    def test_inline_email_tone_resolves_contact_and_send_approves_preview(self):
        SERVICES["notes"].add_note("Aishwarya email: test@example.invalid", "Aishwarya")
        with patch.object(bot.gmail_service, "_deliver_email", return_value="Sent") as deliver:
            result = ai_agent.query_agent("send an email to aishwarya that i miss her and in formal")
            self.assertIn("Email preview — formal", result)
            self.assertIn("test@example.invalid", result)
            self.assertIn("I miss you", result)
            self.assertEqual(ai_agent.query_agent("send"), "Sent")
            deliver.assert_called_once()

    def test_unresolved_recipient_does_not_create_draft(self):
        result = bot.gmail_service.send_email("unknown", "Subject", "Body")
        self.assertIn("provide their email address", result)
        self.assertNotIn(config.ADMIN_USER_ID, bot.gmail_service._drafts)

    def test_revoked_google_access_is_explained_without_raw_error(self):
        service = Mock()
        service.users.return_value.messages.return_value.send.return_value.execute.side_effect = RuntimeError("invalid_grant: Token has been expired or revoked.")
        with patch.object(bot.gmail_service.os.path, "exists", return_value=True), patch("google.oauth2.credentials.Credentials.from_authorized_user_file"), patch("googleapiclient.discovery.build", return_value=service):
            result = bot.gmail_service._deliver_email("test@example.invalid", "Subject", "Body")
        self.assertIn("Google sign-in needs reconnecting", result)
        self.assertNotIn("invalid_grant", result)

    def test_email_requires_tone_preview_and_explicit_confirmation(self):
        gmail = bot.gmail_service
        rewrite = Mock(return_value={"subject": "Thinking of you", "body": "Hi,\n\nI miss you."})
        with patch.object(gmail, "_deliver_email", return_value="Sent") as deliver:
            self.assertIn("Which tone", gmail.send_email("test@example.invalid", "Hi", "I miss you"))
            gmail.handle_email_reply("send email", rewrite)
            deliver.assert_not_called()
            self.assertIn("Email preview", gmail.handle_email_reply("warm", rewrite))
            gmail.handle_email_reply("yes", rewrite)
            deliver.assert_not_called()
            self.assertEqual(gmail.handle_email_reply("send email", rewrite), "Sent")
            gmail.handle_email_reply("send email", rewrite)
            deliver.assert_called_once()

    def test_email_cancel_and_failed_rewrite_do_not_send(self):
        gmail = bot.gmail_service
        gmail.send_email("test@example.invalid", "Hi", "Body")
        with patch.object(gmail, "_deliver_email") as deliver:
            self.assertIn("Nothing was sent", gmail.handle_email_reply("formal", Mock(side_effect=RuntimeError())))
            gmail.handle_email_reply("cancel", Mock())
            self.assertIsNone(gmail.handle_email_reply("send email", Mock()))
            deliver.assert_not_called()

    def test_email_escaped_newlines_become_paragraphs(self):
        from email import message_from_bytes
        service = Mock()
        service.users.return_value.messages.return_value.send.return_value.execute.return_value = {"id": "test-only"}
        with patch.object(bot.gmail_service.os.path, "exists", return_value=True), \
             patch("google.oauth2.credentials.Credentials.from_authorized_user_file"), \
             patch("googleapiclient.discovery.build", return_value=service):
            bot.gmail_service._deliver_email("test@example.invalid", "Test", r"Hi Aishwarya,\n\nI miss you.\n\nWarmly,\nRevanth — ₹")
        raw = service.users.return_value.messages.return_value.send.call_args.kwargs["body"]["raw"]
        message = message_from_bytes(base64.urlsafe_b64decode(raw))
        self.assertEqual(message.get_content_type(), "multipart/alternative")
        plain, html = message.get_payload()
        body = plain.get_payload(decode=True).decode(plain.get_content_charset())
        html_body = html.get_payload(decode=True).decode(html.get_content_charset())
        self.assertIn("<p>Hi Aishwarya,</p>", html_body)
        self.assertEqual(body, "Hi Aishwarya,\n\nI miss you.\n\nWarmly,\nRevanth — ₹")

    def test_invalid_cloud_token_preserves_working_credentials(self):
        token = Path(SANDBOX.name) / "token-test.json"
        token.write_text('{"test": "original"}', encoding="utf-8")
        for invalid in ("not-base64", "{}", "[]", '{"access_token":"incomplete"}'):
            self.assertFalse(config.install_google_token(invalid, str(token)))
            self.assertEqual(token.read_text(encoding="utf-8"), '{"test": "original"}')

    def test_base64_cloud_token_installs_atomically(self):
        token = Path(SANDBOX.name) / "token-test.json"
        data = {"refresh_token": "fake", "client_id": "fake", "client_secret": "fake"}
        encoded = base64.b64encode(json.dumps(data).encode()).decode()
        self.assertTrue(config.install_google_token(encoded, str(token)))
        self.assertEqual(json.loads(token.read_text(encoding="utf-8")), data)

    def test_nested_email_body_prefers_plain_text_and_skips_attachments(self):
        def part(mime, text, **extra):
            return {"mimeType": mime, "body": {"data": base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")}, **extra}
        payload = {"mimeType": "multipart/mixed", "parts": [
            {"mimeType": "multipart/alternative", "parts": [
                part("text/html", "<p>HTML duplicate</p>"), part("text/plain", "Full body beyond the preview")
            ]}, part("text/plain", "Secret attachment", filename="attachment.txt")
        ]}
        self.assertEqual(bot.gmail_service._message_body(payload), "Full body beyond the preview")
        self.assertEqual(bot.gmail_service._message_body(part("text/html", "<p>Hello &amp; welcome</p>")), "Hello & welcome")

    def test_invalid_calendar_time_never_inserts_guessed_event(self):
        service = Mock()
        with patch.object(bot.calendar_service.os.path, "exists", return_value=True), \
             patch("google.oauth2.credentials.Credentials.from_authorized_user_file"), \
             patch("googleapiclient.discovery.build", return_value=service):
            result = bot.calendar_service.add_calendar_event("Meeting", "not a real date")
        self.assertIn("no event was created", result)
        service.events.return_value.insert.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
