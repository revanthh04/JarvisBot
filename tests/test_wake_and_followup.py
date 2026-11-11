from test_regressions import IsolatedTest, SERVICES, OTHER, config, ai_agent
from unittest.mock import patch
from types import SimpleNamespace
import telegram_webhook


class FollowupTests(IsolatedTest):
    def test_time_reply_completes_only_originating_users_reminder(self):
        self.freeze_reminders(12, 34)
        self.assertIn("What time", ai_agent.query_agent("remind me to split dinner"))
        with config.user_context(OTHER):
            self.assertIsNone(ai_agent.direct_request("at 5"))
        self.assertIn("05:00 PM", ai_agent.query_agent("at 5"))
        self.assertIsNone(ai_agent.direct_request("5 pm"))
        self.assertEqual(SERVICES["reminders"].list_active_reminders()[0]["message"], "Split dinner")

    def test_untrusted_webhook_cannot_queue_updates(self):
        with patch.object(telegram_webhook, "_receiver", (None, None, "expected")):
            self.assertEqual(telegram_webhook.receive(SimpleNamespace(path=telegram_webhook.PATH, headers={})), 403)
