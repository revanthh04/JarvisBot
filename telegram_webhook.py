"""Receive Telegram updates on the same HTTP port as the Render health check."""
import asyncio
import hashlib
import hmac
import json
import signal
from telegram import Update

PATH = "/telegram/updates"
_receiver = None


def receive(handler):
    if handler.path != PATH:
        return 404
    if _receiver is None:
        return 503
    app, loop, secret = _receiver
    supplied = handler.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(supplied.encode(), secret.encode()):
        return 403
    try:
        size = int(handler.headers.get("Content-Length", 0))
        if not 0 < size <= 2_000_000:
            return 413
        update = Update.de_json(json.loads(handler.rfile.read(size)), app.bot)
        if update is None:
            return 400
    except (TypeError, ValueError, KeyError):
        return 400
    asyncio.run_coroutine_threadsafe(app.update_queue.put(update), loop).result(timeout=5)
    return 200


async def serve(app, base_url, token):
    global _receiver
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    loop.add_signal_handler(signal.SIGTERM, stop.set)
    secret = hmac.new(token.encode(), b"yobot-telegram-webhook-v1", hashlib.sha256).hexdigest()
    async with app:
        await app.start()
        try:
            _receiver = (app, loop, secret)
            await app.bot.set_webhook(url=base_url.rstrip("/") + PATH, secret_token=secret,
                                      max_connections=4, drop_pending_updates=False)
            await stop.wait()
        finally:
            _receiver = None
            await app.stop()
