"""Offline OAuth ownership, replay, encryption and disconnect regressions."""
import asyncio
import json
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
import time
from unittest.mock import AsyncMock, Mock, patch

from test_regressions import IsolatedTest, SANDBOX, OTHER, THIRD, SERVICES, config, bot, ai_agent
import google_accounts as accounts
import personal_sheets


class GoogleAccountTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        from cryptography.fernet import Fernet
        self.database = str(Path(SANDBOX.name) / ("accounts-" + secrets.token_hex(8) + ".db"))
        self.stack.enter_context(patch.dict(os.environ, {
            "GOOGLE_ACCOUNTS_DATABASE_URL": "", "GOOGLE_ACCOUNTS_SQLITE": self.database,
            "GOOGLE_ACCOUNTS_ENCRYPTION_KEY": Fernet.generate_key().decode(), "RENDER": "",
            "GOOGLE_OAUTH_REDIRECT_URI": "https://example.invalid/google/callback",
            "GOOGLE_OAUTH_WEB_CLIENT_JSON": json.dumps({"web": {"client_id": "test", "client_secret": "fake",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}),
        }))

    def seed_account(self, uid, refresh="fake-refresh"):
        data = {"token": "fake-access", "refresh_token": refresh, "client_id": "test", "client_secret": "fake",
                "token_uri": "https://oauth2.googleapis.com/token", "scopes": accounts.SCOPES,
                "expiry": "2099-01-01T00:00:00Z"}
        with accounts._db() as execute:
            execute("INSERT INTO google_accounts (uid,token,email) VALUES (%s,%s,%s)",
                    (uid, accounts._encrypt(uid, json.dumps(data)), f"user{uid}@example.invalid"))

    def test_guest_credentials_never_fall_back_to_admin(self):
        config.set_current_user(OTHER)
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file") as legacy:
            with self.assertRaises(accounts.NotConnected):
                accounts.credentials()
            legacy.assert_not_called()

    def test_encrypted_tokens_are_bound_to_their_owner(self):
        self.seed_account(OTHER)
        row = accounts._record(OTHER)
        self.assertNotIn("fake-refresh", row[0])
        self.assertIn("fake-refresh", accounts._decrypt(OTHER, row[0]))
        with self.assertRaises(accounts.NotConnected):
            accounts._decrypt(THIRD, row[0])
        config.set_current_user(OTHER)
        self.assertEqual(accounts.credentials().refresh_token, "fake-refresh")

    def test_render_refuses_ephemeral_account_database(self):
        with patch.dict(os.environ, {"RENDER": "true"}):
            self.assertFalse(accounts.setup_ready())
            with self.assertRaises(accounts.NotConnected):
                with accounts._db():
                    pass

    def test_confirmation_is_owner_bound_expiring_and_single_use(self):
        self.seed_account(OTHER)
        token = accounts._record(OTHER)[0]
        with accounts._db() as execute:
            execute("INSERT INTO google_oauth_pending (state_hash,uid,verifier,expires,confirmation_hash,token,email) VALUES ('state',%s,'',%s,%s,%s,'new@example.invalid')",
                    (OTHER, int(time.time()) + 600, accounts._hash("confirm-code"), token))
        config.set_current_user(THIRD)
        self.assertIn("invalid or expired", accounts.confirm_connection("confirm-code"))
        config.set_current_user(OTHER)
        self.assertIn("new@example.invalid", accounts.confirm_connection("confirm-code"))
        self.assertIn("invalid or expired", accounts.confirm_connection("confirm-code"))

    def test_expired_confirmation_never_links_account(self):
        with accounts._db() as execute:
            execute("INSERT INTO google_oauth_pending (state_hash,uid,verifier,expires,confirmation_hash,token,email) VALUES ('old',%s,'',%s,%s,'fake','x@example.invalid')",
                    (OTHER, int(time.time()) - 1, accounts._hash("old")))
        config.set_current_user(OTHER)
        self.assertIn("invalid or expired", accounts.confirm_connection("old"))
        self.assertFalse(accounts.connected())

    def test_callback_state_is_single_use_and_does_not_link_before_confirmation(self):
        config.set_current_user(OTHER)
        flow = Mock()
        flow.code_verifier = "pkce-test"
        flow.authorization_url.return_value = ("https://accounts.google.com/test", "state")
        flow.credentials.refresh_token = "fake-refresh"
        flow.credentials.token = "fake-access"
        flow.credentials.granted_scopes = accounts.SCOPES
        flow.credentials.to_json.return_value = json.dumps({"refresh_token": "fake-refresh"})
        response = Mock()
        response.json.return_value = {"email_verified": True, "email": "guest@example.invalid"}
        with patch("google_auth_oauthlib.flow.Flow.from_client_config", return_value=flow) as factory, patch("requests.get", return_value=response):
            self.assertIn("personal Google sign-in link", accounts.begin_connection())
            state = factory.call_args.kwargs["state"]
            message = accounts.oauth_callback({"state": [state], "code": ["fake-code"]})
            self.assertIn("/confirmgoogle", message)
            self.assertFalse(accounts.connected())
            self.assertIn("already used", accounts.oauth_callback({"state": [state], "code": ["fake-code"]}))
            flow.fetch_token.assert_called_once_with(code="fake-code", timeout=20)
            self.assertEqual(factory.call_args.kwargs["code_verifier"], "pkce-test")

    def test_disconnect_revokes_only_current_user_and_blocks_legacy_fallback(self):
        self.seed_account(OTHER)
        self.seed_account(THIRD, "other-refresh")
        config.set_current_user(OTHER)
        with patch("requests.post", return_value=SimpleNamespace(status_code=200)) as revoke:
            self.assertIn("disconnected", accounts.disconnect())
            self.assertEqual(revoke.call_args.kwargs["data"], {"token": "fake-refresh"})
        self.assertFalse(accounts.connected())
        with self.assertRaises(accounts.NotConnected):
            accounts.credentials()
        config.set_current_user(THIRD)
        self.assertTrue(accounts.connected())
        self.assertEqual(accounts.credentials().refresh_token, "other-refresh")

    def test_connected_guest_catalog_keeps_workstation_and_owner_sheets_private(self):
        self.seed_account(OTHER)
        config.set_current_user(OTHER)
        modules = {fn.__module__ for fn in ai_agent.get_available_tools()}
        self.assertTrue({"gmail_service", "calendar_service", "personal_sheets"}.issubset(modules))
        self.assertFalse(modules & {"device_service", "sheets_service", "linkedin_service"})

    def test_personal_sheets_exports_only_current_users_rows(self):
        SERVICES["notes"].add_note("owner secret", "private")
        self.seed_account(OTHER)
        config.set_current_user(OTHER)
        SERVICES["notes"].add_note("guest record", "mine")
        api = Mock()
        sheets = api.spreadsheets.return_value
        sheets.create.return_value.execute.return_value = {"spreadsheetId": "guest-sheet"}
        sheets.get.return_value.execute.return_value = {"sheets": [{"properties": {"title": name, "sheetId": i,
            "gridProperties": {"rowCount": 100, "columnCount": 26}}} for i, name in enumerate(accounts_backup_names())]}
        with patch("googleapiclient.discovery.build", return_value=api):
            self.assertIn("exported", personal_sheets.sync_personal_sheets())
        payload = json.dumps(sheets.batchUpdate.call_args.kwargs["body"])
        self.assertIn("guest record", payload)
        self.assertNotIn("owner secret", payload)
        self.assertEqual(accounts.sheet_id(), "guest-sheet")
        config.set_current_user(THIRD)
        with self.assertRaises(accounts.NotConnected):
            accounts.sheet_id()

    def test_google_signin_links_are_not_sent_in_groups(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=OTHER, first_name="Guest"),
            effective_chat=SimpleNamespace(type="group"), message=SimpleNamespace(text="/connectgoogle", reply_text=AsyncMock()))
        with patch.object(accounts, "begin_connection") as begin:
            asyncio.run(bot.cmd_google(update, SimpleNamespace(args=[])))
            begin.assert_not_called()
        self.assertIn("private YoBot chat", update.message.reply_text.call_args.args[0])


def accounts_backup_names():
    import backup_service
    return backup_service.DATABASES
