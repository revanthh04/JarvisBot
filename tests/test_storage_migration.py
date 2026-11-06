from datetime import datetime
import importlib
from unittest.mock import Mock, patch

from test_regressions import IsolatedTest, config, sheets_service
from test_sheets_store import FakeSheets, sample_tables
import manage_sheets_store as migration


class StorageMigrationTests(IsolatedTest):
    def test_live_fence_probe_leaves_no_named_ranges_or_cell_changes(self):
        from googleapiclient.errors import HttpError
        from httplib2 import Response
        api = FakeSheets()
        # The live probe uses a real HttpError; model duplicate-ID failure the
        # same way as Google while retaining FakeSheets atomic behavior.
        initial = api.apply_batch
        def apply(body):
            try:
                return initial(body)
            except ValueError:
                raise HttpError(Response({"status": "400"}), b'{"error":{"message":"Duplicate named range"}}')
        api.apply_batch = apply
        meta = {"sheets": [{"properties": {"sheetId": 100, "title": "Existing"}}]}
        # Seed a grid using the same public request path as the storage adapter.
        initial({"requests": [{"addSheet": {"properties": {"sheetId": 100, "title": "Existing", "gridProperties": {"rowCount": 100,"columnCount": 26}}}}]})
        before = api.rows("Existing")
        self.assertTrue(migration.probe_fence(api, "fake", meta)["atomic_validation_verified"])
        self.assertEqual(api.rows("Existing"), before)
        self.assertEqual(api.named_ranges, {})

    def test_initial_migration_closes_old_local_alerts_and_preserves_future(self):
        tables = sample_tables()
        row = tables["reminders"][0]
        row["remind_at"] = "2026-10-01T10:00:00+05:30"
        clock = Mock(wraps=datetime)
        clock.now.return_value = config.get_tz().localize(datetime(2026, 11, 6, 12))
        with patch.object(migration, "datetime", clock):
            result = migration.sanitize_initial_reminders(tables)
        self.assertEqual(result["historical_reminders_closed"], 1)
        self.assertEqual(row["triggered"], 1)
        self.assertIsNone(row["last_triggered_at"])

    def test_failed_refresh_reports_disconnected_not_linked(self):
        from google.auth.exceptions import RefreshError
        creds = Mock(expired=True, refresh_token="fake")
        creds.refresh.side_effect = RefreshError("private OAuth diagnostic")
        with patch.object(sheets_service.os.path, "exists", return_value=True), patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=creds):
            self.assertEqual(sheets_service.get_credentials(), (None, "auth_expired"))
