import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from test_regressions import IsolatedTest, bot, config


class RepairTests(IsolatedTest):
    def test_pending_incident_backs_off_and_announces_verified_recovery(self):
        job = SimpleNamespace(data={})
        ctx = SimpleNamespace(job=job, bot=SimpleNamespace(send_message=AsyncMock()))
        with patch.object(config, "SHEETS_DURABLE_STORAGE", True), patch.object(bot.sheets_store, "health_status", return_value={"pending": True}), patch.object(bot.sheets_store, "sync_now", side_effect=[{"status":"pending"}, {"status":"success"}]) as sync:
            asyncio.run(bot.recover_pending_save(ctx))
            asyncio.run(bot.recover_pending_save(ctx))
            self.assertEqual(sync.call_count, 1)
            job.data["next"] = 0
            asyncio.run(bot.recover_pending_save(ctx))
            self.assertEqual(ctx.bot.send_message.await_count, 2)
            self.assertEqual(job.data, {})
