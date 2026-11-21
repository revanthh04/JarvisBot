"""Private Telegram relay for the owner's first linked contact."""
import re
import sqlite3
from pathlib import Path

from telegram import ForceReply
from telegram.error import TelegramError

import config

AISHWARYA = 8222441411
LINK = "Connect me to Revanth"
DB = Path("telegram_connections.db")
NAMES = {config.ADMIN_USER_ID: "Revanth", AISHWARYA: "Aishwarya"}


def connection(user_id, enable=None):
    with sqlite3.connect(DB) as db:
        db.execute("CREATE TABLE IF NOT EXISTS linked (user_id INTEGER PRIMARY KEY)")
        if enable is True:
            db.execute("INSERT OR IGNORE INTO linked VALUES (?)", (user_id,))
        elif enable is False:
            db.execute("DELETE FROM linked WHERE user_id=?", (user_id,))
        return bool(db.execute("SELECT 1 FROM linked WHERE user_id=?", (user_id,)).fetchone())


async def handle(update, context):
    msg = update.message
    uid = update.effective_user.id
    if uid not in NAMES or update.effective_chat.type != "private":
        return False
    text = (msg.text or "").strip()
    if uid == AISHWARYA and text.casefold() in {LINK.casefold(), "disconnect from revanth"}:
        enabled = text.casefold() == LINK.casefold()
        connection(uid, enabled)
        await msg.reply_text("Connected. You can now message Revanth through YoBot. To stop, say ‘disconnect from Revanth’." if enabled else "Disconnected from Revanth.")
        return True

    peer = AISHWARYA if uid == config.ADMIN_USER_ID else config.ADMIN_USER_ID
    original = msg.reply_to_message
    prefix = f"Telegram message from {NAMES[peer]}:\n"
    if (original and original.from_user and original.from_user.id == context.bot.id
            and (original.text or "").startswith(prefix)):
        body = text
    else:
        match = re.fullmatch(r"(?:please\s+)?(?:tell|ask|message|send a (?:telegram )?message to)\s+"
                             r"(Aishwarya(?: Patil)?|Revanth)(?:\s*[:,]\s*|\s+)(.+)", text, re.I | re.S)
        if not match or match[1].split()[0].casefold() != NAMES[peer].casefold():
            return False
        body = match[2].strip()
    if not config.is_authorized(peer) or not connection(AISHWARYA):
        await msg.reply_text("Aishwarya can enable private messages by sending YoBot: Connect me to Revanth")
        return True
    outgoing = f"Telegram message from {NAMES[uid]}:\n{body}"
    if len(outgoing.encode("utf-16-le")) // 2 > 4096:
        await msg.reply_text("Please shorten the message so it fits in one Telegram message.")
        return True
    try:
        await context.bot.send_message(chat_id=peer, text=outgoing,
                                       reply_markup=ForceReply(input_field_placeholder="Type your reply"))
    except TelegramError:
        await msg.reply_text("Telegram delivery could not be confirmed.")
    else:
        await msg.reply_text(f"Sent to {NAMES[peer]} on Telegram.")
    return True
