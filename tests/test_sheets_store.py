"""Offline durability checks with a transactional in-memory Sheets API.

The existing regression harness copies source files and databases into a temporary
workspace and blocks all network access. No real workbook or account is used.
"""
import asyncio
from contextlib import closing
from copy import deepcopy
import io
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from test_regressions import IsolatedTest, SERVICES, OTHER, config, backup_service, bot
import sheets_store as store


class Request:
    def __init__(self, execute):
        self.execute = execute


class FakeSheets:
    """Model the atomicity and value semantics used by the persistence adapter."""
    def __init__(self):
        self.sheets = {}
        self.named_ranges = {}
        self.attempts = 0
        self.commits = 0
        self.fail_next = False
        self.timeout_after_commit = False
        self.before_batch = None

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, **kwargs):
        return Request(lambda: self.meta())

    def meta(self):
        return {"sheets": [{"properties": deepcopy(sheet["properties"])} for sheet in self.sheets.values()],
                "namedRanges": deepcopy(list(self.named_ranges.values()))}

    def batchGet(self, *, ranges, **kwargs):
        def execute():
            result = []
            for cell_range in ranges:
                title = cell_range.split("!", 1)[0].strip("'")
                sheet = next(s for s in self.sheets.values() if s["properties"]["title"] == title)
                rows = deepcopy(sheet["rows"])
                # Sheets omits trailing empty cells and completely empty rows.
                for row in rows:
                    while row and row[-1] == "":
                        row.pop()
                while rows and not rows[-1]:
                    rows.pop()
                result.append({"range": cell_range, "values": rows})
            return {"valueRanges": result}
        return Request(execute)

    def batchUpdate(self, *, body, **kwargs):
        return Request(lambda: self.apply_batch(body))

    def apply_batch(self, body):
        self.attempts += 1
        if self.before_batch:
            callback, self.before_batch = self.before_batch, None
            callback()
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("Simulated unavailable API")
        sheets, named = deepcopy(self.sheets), deepcopy(self.named_ranges)
        for request in body["requests"]:
            if "deleteNamedRange" in request:
                range_id = request["deleteNamedRange"]["namedRangeId"]
                named.pop(range_id, None)  # Live Sheets deletion is idempotent.
            elif "addNamedRange" in request:
                value = deepcopy(request["addNamedRange"]["namedRange"])
                if value["namedRangeId"] in named or any(n["name"] == value["name"] for n in named.values()):
                    raise ValueError("Named range already exists")
                named[value["namedRangeId"]] = value
            elif "addSheet" in request:
                props = deepcopy(request["addSheet"]["properties"])
                if props["sheetId"] in sheets or any(s["properties"]["title"] == props["title"] for s in sheets.values()):
                    raise ValueError("Sheet already exists")
                sheets[props["sheetId"]] = {"properties": props, "rows": []}
            elif "appendDimension" in request:
                req = request["appendDimension"]
                key = "rowCount" if req["dimension"] == "ROWS" else "columnCount"
                sheets[req["sheetId"]]["properties"]["gridProperties"][key] += req["length"]
            elif "updateCells" in request:
                req = request["updateCells"]
                assert req["fields"] == "userEnteredValue"
                assert set(req["range"]) == {"sheetId"}
                rows = []
                for row in req["rows"]:
                    values = []
                    for cell in row["values"]:
                        value = cell.get("userEnteredValue", {})
                        assert "formulaValue" not in value, "User data must remain literal"
                        values.append(value.get("stringValue", value.get("numberValue", "")))
                    rows.append(values)
                # A range covering the whole sheet clears trailing values atomically.
                sheets[req["range"]["sheetId"]]["rows"] = rows
            elif "repeatCell" in request or "addProtectedRange" in request:
                pass
            else:
                raise AssertionError(f"Unhandled fake Sheets operation: {list(request)}")
        self.sheets, self.named_ranges = sheets, named
        self.commits += 1
        if self.timeout_after_commit:
            self.timeout_after_commit = False
            raise TimeoutError("Response lost after atomic commit")
        return {"replies": [{} for _ in body["requests"]]}

    def rows(self, title):
        return next(s["rows"] for s in self.sheets.values() if s["properties"]["title"] == title)


def sample_tables(owner=None, row_id=101):
    owner = config.ADMIN_USER_ID if owner is None else owner
    stamp = "2026-11-03 20:15:00"
    return {
        "expenses": [{"id": row_id, "user_id": owner, "amount": 123.45, "category": "Food",
                      "description": "Lunch ₹ — తెలుగు", "expense_date": "2026-11-03", "created_at": stamp}],
        "books": [{"id": row_id, "user_id": owner, "title": "A Book", "author": "", "status": "Reading",
                   "current_page": 12, "total_pages": 100, "rating": 4.5, "notes": None,
                   "created_at": stamp, "updated_at": stamp}],
        "notes": [{"id": row_id, "user_id": owner, "title": "", "content": "=SUM(A1:A4)\nతెలుగు 😀",
                   "tags": None, "created_at": stamp}],
        "tasks": [{"id": row_id, "user_id": owner, "title": "Task", "due_date": None,
                   "completed": 0, "created_at": stamp}],
        "habits": [{"id": row_id, "user_id": owner, "name": "Read", "created_at": "2026-11-03"}],
        "habit_logs": [{"id": row_id, "habit_id": row_id, "log_date": "2026-11-03"}],
        "reminders": [{"id": row_id, "user_id": owner, "message": "Future meeting", "remind_at": "2027-01-01T10:00:00+05:30",
                       "triggered": 0, "repeat_interval_minutes": 0, "is_recurring": 0,
                       "last_triggered_at": None, "created_at": stamp}],
    }


class DurableStoreTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(config, "SHEETS_DURABLE_STORAGE", True))
        for name, value in {"_ready": False, "_pending": False, "_revision": None,
                            "_digest": None, "_attempt": None, "_last_sync": None}.items():
            self.stack.enter_context(patch.object(store, name, value))
        self.api = FakeSheets()
        self.stack.enter_context(patch.object(store, "connect", return_value=(self.api, "fake-workbook")))

    def seed_remote(self, tables=None):
        tables = sample_tables() if tables is None else tables
        body, state = store.batch_for_snapshot(tables, self.api.meta())
        self.api.apply_batch(body)
        return state

    def remote_tables(self):
        return store.read_remote(self.api, "fake-workbook")[1]

    def test_complete_roundtrip_preserves_types_unicode_history_and_literals(self):
        expected = sample_tables()
        self.seed_remote(expected)
        result = store.restore_on_startup()
        self.assertEqual(result["status"], "restored")
        self.assertEqual(store.admin_tables(backup_service.read_snapshot()), expected)
        self.assertIsNone(SERVICES["tasks"].list_tasks()[0]["due_date"])
        self.assertEqual(self.api.rows("Notes")[1][2], "=SUM(A1:A4)\nతెలుగు 😀")
        self.assertEqual(self.api.rows("_store_notes")[1][2], '""')
        self.assertEqual(self.api.rows("_store_notes")[1][4], "null")
        self.assertTrue(store.health_status()["ready"])

    def test_empty_remote_tables_replace_stale_cache_without_resurrection(self):
        stale = sample_tables()
        self.seed_remote(stale)
        store.restore_on_startup()
        empty = {name: [] for name in store.TABS}
        store.replace_local(empty)
        self.assertEqual(store.sync_now()["status"], "success")
        self.assertEqual(self.remote_tables(), empty)
        self.assertEqual(len(self.api.rows("Notes")), 1)
        # Simulate a redeploy that has checked-in, outdated SQLite files.
        store.replace_local(stale)
        store._ready = False
        store.restore_on_startup()
        self.assertEqual(store.admin_tables(backup_service.read_snapshot()), empty)
        self.assertEqual(SERVICES["reminders"].list_active_reminders(), [])

    def test_admin_export_excludes_guests_and_restore_preserves_their_rows(self):
        expected = sample_tables()
        self.seed_remote(expected)
        guests = sample_tables(owner=OTHER, row_id=901)
        for name, rows in guests.items():
            meta = backup_service.DATABASES[name]
            cols = meta["columns"]
            with closing(sqlite3.connect(meta["file"])) as conn:
                conn.executemany(f"INSERT INTO {name} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                                 [[row[col] for col in cols] for row in rows])
                conn.commit()
        store.restore_on_startup()
        snapshot = backup_service.read_snapshot()
        self.assertEqual(store.admin_tables(snapshot), expected)
        self.assertTrue(all(len(rows) == 2 for rows in snapshot["tables"].values()))
        with config.user_context(OTHER):
            SERVICES["notes"].add_note("Guest secret", "Guest")
        self.assertEqual(self.remote_tables(), expected)
        self.assertEqual(store.warning_text(OTHER), "")

    def test_corrupt_remote_fails_before_any_local_cache_write(self):
        self.seed_remote()
        store.restore_on_startup()
        before = backup_service.read_snapshot()["tables"]
        self.api.rows("_store_notes")[1][3] = json.dumps("Manual edit without updated checksum")
        with patch.object(store, "replace_local", wraps=store.replace_local) as replace:
            with self.assertRaisesRegex(ValueError, "checksum"):
                store.restore_on_startup()
            replace.assert_not_called()
        self.assertEqual(backup_service.read_snapshot()["tables"], before)
        self.assertFalse(store.health_status()["ready"])

    def test_uninitialized_store_refuses_upload_and_missing_remote_refuses_recovery(self):
        result = store.persist({"tables": sample_tables()})
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.api.attempts, 0)
        with self.assertRaisesRegex(ValueError, "missing"):
            store.restore_on_startup()
        self.assertEqual(self.api.attempts, 0)

    def test_stale_revision_never_overwrites_a_newer_snapshot(self):
        state = self.seed_remote()
        store.restore_on_startup()
        newer = sample_tables()
        newer["notes"][0]["content"] = "Newer writer"
        body, newer_state = store.batch_for_snapshot(newer, self.api.meta(), previous=state["revision"])
        self.api.apply_batch(body)
        before_attempts = self.api.attempts
        result = store.persist({"tables": sample_tables()})
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.api.attempts, before_attempts)
        self.assertEqual(self.remote_tables(), newer)
        self.assertEqual(store.read_remote(self.api, "fake-workbook")[0]["revision"], newer_state["revision"])

    def test_named_range_fence_rejects_race_atomically(self):
        state = self.seed_remote()
        store.restore_on_startup()
        ours, competing = sample_tables(), sample_tables()
        ours["notes"][0]["content"] = "Our pending update"
        competing["notes"][0]["content"] = "Other writer won the race"
        competing_body, _ = store.batch_for_snapshot(competing, self.api.meta(), previous=state["revision"])
        self.api.before_batch = lambda: self.api.apply_batch(competing_body)
        result = store.persist({"tables": ours})
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.api.commits, 2)  # bootstrap plus the competing writer only
        self.assertEqual(self.remote_tables(), competing)
        self.assertEqual(self.api.rows("Notes")[1][2], "Other writer won the race")

    def test_timeout_after_success_is_recognized_without_duplicate_write(self):
        self.seed_remote()
        store.restore_on_startup()
        changed = sample_tables()
        changed["tasks"][0]["completed"] = 1
        self.api.timeout_after_commit = True
        self.assertEqual(store.persist({"tables": changed})["status"], "pending")
        self.assertEqual(self.remote_tables(), changed)
        before_attempts = self.api.attempts
        self.assertEqual(store.persist({"tables": changed})["status"], "success")
        self.assertEqual(self.api.attempts, before_attempts)
        self.assertFalse(store.health_status()["pending"])
        self.assertEqual(store.warning_text(), "")

    def test_failed_write_preserves_snapshot_warns_and_retries_local_mutation(self):
        empty = {name: [] for name in store.TABS}
        self.seed_remote(empty)
        store.restore_on_startup()
        self.api.fail_next = True
        result = SERVICES["notes"].add_note("Must survive", "Saved locally")
        self.assertIn("id", result)
        self.assertEqual(self.remote_tables(), empty)
        self.assertTrue(store.health_status()["pending"])
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
        asyncio.run(bot.send_rich_reply(update, "Added your note."))
        self.assertIn("save is pending", update.message.reply_text.call_args.args[0])
        with config.user_context(OTHER):
            self.assertEqual(store.warning_text(), "")
        self.assertEqual(store.sync_now()["status"], "success")
        self.assertEqual(len(self.remote_tables()["notes"]), 1)
        self.assertEqual(self.remote_tables()["notes"][0]["content"], "Must survive")
        self.assertEqual(store.warning_text(), "")

    def test_voice_pending_save_warning_is_spoken_and_sent_as_text(self):
        store.mark_pending()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=config.ADMIN_USER_ID, first_name="Admin"),
            effective_chat=SimpleNamespace(id=config.ADMIN_USER_ID),
            message=SimpleNamespace(voice=SimpleNamespace(file_id="voice"), audio=None,
                                    reply_text=AsyncMock(), reply_voice=AsyncMock()))
        context = SimpleNamespace(bot=SimpleNamespace(
            send_chat_action=AsyncMock(), get_file=AsyncMock(return_value=SimpleNamespace(download_to_memory=AsyncMock()))))
        with patch.object(bot.ai_agent, "transcribe_audio", return_value="Add a task"), \
             patch.object(bot.ai_agent, "query_agent", return_value="Task added."), \
             patch.object(bot.voice_service, "text_to_speech", new=AsyncMock(side_effect=RuntimeError("Stop before file access"))) as speak:
            asyncio.run(bot.handle_voice(update, context))
        self.assertIn("save is pending", speak.call_args.args[0])
        self.assertIn("save is pending", update.message.reply_text.call_args_list[0].args[0])

    def test_startup_recovery_failure_prevents_polling_and_reconciliation(self):
        with patch.object(store, "restore_on_startup", side_effect=ValueError("sensitive API details")), \
             patch.object(bot, "ApplicationBuilder") as builder, \
             patch.object(SERVICES["reminders"], "reconcile_overdue_at_startup") as reconcile:
            with self.assertRaisesRegex(RuntimeError, "recovery failed") as error:
                bot.main()
            self.assertNotIn("sensitive", str(error.exception))
            builder.assert_not_called()
            reconcile.assert_not_called()

    def test_startup_pending_reconciliation_save_prevents_polling(self):
        def reconcile():
            store.mark_pending()
            return {"expired": 1, "rescheduled": 0}
        self.seed_remote()
        with patch.object(SERVICES["reminders"], "reconcile_overdue_at_startup", side_effect=reconcile), \
             patch.object(bot, "ApplicationBuilder") as builder, patch.object(bot, "start_health_server") as health:
            with self.assertRaisesRegex(RuntimeError, "startup save is incomplete"):
                bot.main()
            builder.assert_not_called()
            health.assert_not_called()

    def test_health_endpoint_reports_unready_store_without_private_details(self):
        handler = object.__new__(bot.HealthCheckHandler)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = io.BytesIO()
        handler.do_GET()
        handler.send_response.assert_called_once_with(503)
        payload = json.loads(handler.wfile.getvalue())
        self.assertEqual(set(payload["storage"]), {"enabled", "ready", "pending", "last_sync"})
        self.assertEqual(payload["status"], "unavailable")
