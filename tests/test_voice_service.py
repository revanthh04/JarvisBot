"""Offline tests for free speech output and temporary audio cleanup."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import voice_service


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_returns_nonempty_audio(self):
        async def save(path):
            Path(path).write_bytes(b"test audio")
        with patch.object(voice_service.edge_tts, "Communicate") as communicate:
            communicate.return_value.save = AsyncMock(side_effect=save)
            path = await voice_service.text_to_speech("**Hello YoBot**")
        try:
            self.assertEqual(Path(path).read_bytes(), b"test audio")
            self.assertEqual(communicate.call_args.args[0], "Hello YoBot")
        finally:
            os.remove(path)

    async def test_failure_and_cancellation_remove_partial_file(self):
        for error in (RuntimeError("offline"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                original = tempfile.NamedTemporaryFile
                def temporary_file(**kwargs):
                    return original(dir=directory, **kwargs)
                with patch.object(voice_service.tempfile, "NamedTemporaryFile", side_effect=temporary_file), \
                        patch.object(voice_service.edge_tts, "Communicate") as communicate:
                    communicate.return_value.save = AsyncMock(side_effect=error)
                    with self.assertRaises(type(error)):
                        await voice_service.text_to_speech("Hello")
                self.assertEqual(list(Path(directory).iterdir()), [])

    async def test_empty_audio_rejected(self):
        with patch.object(voice_service.edge_tts, "Communicate") as communicate:
            communicate.return_value.save = AsyncMock()
            with self.assertRaisesRegex(RuntimeError, "empty audio"):
                await voice_service.text_to_speech("Hello")

    async def test_long_reply_does_not_call_provider(self):
        with patch.object(voice_service.edge_tts, "Communicate") as communicate:
            with self.assertRaises(ValueError):
                await voice_service.text_to_speech("a" * 3001)
            communicate.assert_not_called()

    async def test_sync_wrapper_does_not_retry_failed_request(self):
        with patch.object(voice_service, "text_to_speech", new_callable=AsyncMock,
                          side_effect=RuntimeError("offline")) as speak:
            with self.assertRaises(RuntimeError):
                voice_service.synthesize_sync("Hello")
            speak.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
