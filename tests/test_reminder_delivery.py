import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from test_regressions import IsolatedTest, SERVICES, OTHER, config, bot, ai_agent


class ReminderDeliveryTests(IsolatedTest):
    def test_exact_followup_is_saved_for_each_user_and_delivered_to_correct_chat(self):
        now = self.freeze_reminders(13, 22)
        service = SERVICES["reminders"]
        with patch.object(ai_agent, "query_gemini_agent") as model:
            for uid in (config.ADMIN_USER_ID, OTHER):
                with config.user_context(uid):
                    reply = ai_agent.query_agent("and remind me at 2pm to start sloving problems on tai for tidays company task")
                    self.assertIn("02:00 PM", reply)
                    saved = service.list_active_reminders()
                    self.assertEqual(len(saved), 1)
                    self.assertIn("tai", saved[0]["message"].lower())
                    self.assertNotIn("And remind", saved[0]["message"])
            model.assert_not_called()
        self.freeze_reminders(14, 0)
        ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        asyncio.run(bot.check_reminders_job(ctx))
        self.assertEqual({c.kwargs["chat_id"] for c in ctx.bot.send_message.call_args_list}, {config.ADMIN_USER_ID, OTHER})
        asyncio.run(bot.check_reminders_job(ctx))
        self.assertEqual(ctx.bot.send_message.await_count, 2)

    def test_model_cannot_confirm_a_reminder_without_successful_write(self):
        session = Mock()
        session.send_message.return_value = SimpleNamespace(text="Reminder set for 2 PM today!")
        with patch.object(ai_agent, "get_or_create_chat_session", return_value=session):
            result = ai_agent.query_gemini_agent("set a reminder to call Mom at 2pm")
        self.assertIn("could not verify", result)
        self.assertEqual(SERVICES["reminders"].list_active_reminders(), [])

    def test_model_failure_after_write_does_not_repeat_side_effect(self):
        self.freeze_reminders(13, 0)
        session = Mock()
        def perform(_):
            SERVICES["reminders"].create_reminder("Call Mom", delay_minutes=2)
            raise RuntimeError("Model response failed after tool execution")
        session.send_message.side_effect = perform
        with patch.object(ai_agent, "get_or_create_chat_session", return_value=session):
            result = ai_agent.query_gemini_agent("set a reminder to call Mom in 2 minutes")
        self.assertIn("Reminder set", result)
        session.send_message.assert_called_once()
        self.assertEqual(len(SERVICES["reminders"].list_active_reminders()), 1)

    def test_missing_history_never_claims_it_was_not_scheduled(self):
        result = ai_agent.query_agent("you did not remind me at 2 ig")
        self.assertIn("does not prove", result)
        self.assertIn("lost its local records", result)

    def test_delivery_failure_stays_pending_and_history_is_user_isolated(self):
        self.freeze_reminders(13, 0)
        service = SERVICES["reminders"]
        with config.user_context(OTHER):
            result = service.create_reminder("Guest private task", delay_minutes=2)
        self.freeze_reminders(13, 3)
        ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("offline"))))
        asyncio.run(bot.check_reminders_job(ctx))
        with config.user_context(OTHER):
            self.assertEqual(service.get_reminder_history()[0]["state"], "pending")
        self.assertNotIn("Guest private task", service.describe_reminder_history())

    def test_durable_restart_catches_up_instead_of_discarding_overdue_reminders(self):
        self.freeze_reminders(13, 0)
        service = SERVICES["reminders"]
        service.create_reminder("Real durable reminder", delay_minutes=2)
        self.freeze_reminders(13, 5)
        with patch.object(config, "SHEETS_DURABLE_STORAGE", True):
            self.assertEqual(service.reconcile_overdue_at_startup(), {"expired": 0, "rescheduled": 0})
        self.assertEqual(len(service.get_due_reminders()), 1)

    def test_ephemeral_confirmation_discloses_restart_risk(self):
        self.freeze_reminders()
        result = SERVICES["reminders"].create_reminder("Water", delay_minutes=2)
        self.assertIn("restart or deployment can erase", result["status"])
