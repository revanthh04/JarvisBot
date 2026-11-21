"""Private Telegram relay for the owner's first linked contact."""
from contextlib import closing
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
    if config.SHEETS_DURABLE_STORAGE:
        return cloud_state("linked" if enable is None else ("connect" if enable else "disconnect"))
    with closing(sqlite3.connect(DB)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS linked (user_id INTEGER PRIMARY KEY)")
        if enable is True:
            db.execute("INSERT OR IGNORE INTO linked VALUES (?)", (user_id,))
        elif enable is False:
            db.execute("DELETE FROM linked WHERE user_id=?", (user_id,))
        return bool(db.execute("SELECT 1 FROM linked WHERE user_id=?", (user_id,)).fetchone())


def pending(action, body=None):
    if config.SHEETS_DURABLE_STORAGE:
        return cloud_state(action, body)
    # One outstanding message for the owner-to-Aishwarya link.
    with closing(sqlite3.connect(DB)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS pending (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM pending WHERE id=1").fetchone()
        if action == "save" and not row:
            db.execute("INSERT INTO pending VALUES (1,?)", (body,))
        if action == "take" and row:
            db.execute("DELETE FROM pending WHERE id=1")
        return row[0] if row else None


def cloud_state(action, body=None):
    import sheets_store
    service, sid = sheets_store.connect()
    values = service.spreadsheets().values()
    target = "'_telegram_relay'!A1:B1"
    rows = values.get(spreadsheetId=sid, range=target).execute().get("values", [])
    linked, queued = ((rows[0] if rows else []) + ["", ""])[:2]
    if action == "linked":
        return linked == "connected"
    if action == "peek":
        return queued
    if action == "save" and queued:
        return queued
    if action == "connect":
        linked = "connected"
    elif action == "disconnect":
        linked, queued = "", ""
    elif action == "save":
        queued = body
    elif action == "take":
        queued = ""
    values.update(spreadsheetId=sid, range=target, valueInputOption="RAW",
                  body={"values": [[linked, queued]]}).execute()
    return rows[0][1] if action == "take" and rows and len(rows[0]) > 1 else None


def parse_message(text, peer):
    name = r"(?:Aishwarya(?: Patil)?|Ishwarya|Ayshorya|Aishwarya|my girlfriend|my girl friend)" if peer == AISHWARYA else r"Revanth(?: Sir)?"
    start = r"(?:please\s+)?"
    for pattern in (
        start + r"(?:tell|ask|message|text|send (?:a |the )?(?:telegram )?message to)\s+" + name + r"(?:\s*[:,]\s*|\s+)(.+)",
        start + r"send\s+(.+?)\s+to\s+" + name + r"[.!]?",
    ):
        m = re.fullmatch(pattern, text, re.I | re.S)
        if m:
            return m[1].strip().strip('“”"')
    if re.search(r"\bto\s+" + name + r"\b", text, re.I):
        resend = re.search(r'\bplease (?:re)?send(?: (?:it|us|her|him|again|immediately))*[, :]+"([^"]+)"[.!]?$', text, re.I)
        if resend:
            return resend[1]
    return None


async def deliver(bot, uid, peer, body):
    await bot.send_message(chat_id=peer, text=f"Telegram message from {NAMES[uid]}:\n{body}",
                           reply_markup=ForceReply(input_field_placeholder="Type your reply"))


async def handle(update, context, transcript=None):
    msg = update.message
    uid = update.effective_user.id
    if uid not in NAMES or update.effective_chat.type != "private":
        return False
    text = (transcript or msg.text or "").strip()
    connect = re.fullmatch(r"connect me(?: to|,)?\s+revanth[.!]?", text, re.I)
    if uid == AISHWARYA and (connect or text.casefold() == "disconnect from revanth"):
        enabled = bool(connect)
        connection(uid, enabled)
        queued = pending("take")
        await msg.reply_text("Connected. You can now say ‘Send hello to Revanth’." if enabled else "Disconnected.")
        if enabled and queued and config.is_authorized(config.ADMIN_USER_ID):
            try:
                await deliver(context.bot, config.ADMIN_USER_ID, uid, queued)
            except TelegramError:
                status = "Telegram delivery of your waiting message could not be confirmed."
            else:
                status = "Sent your waiting message to Aishwarya on Telegram."
            await context.bot.send_message(chat_id=config.ADMIN_USER_ID, text=status)
        return True

    peer = AISHWARYA if uid == config.ADMIN_USER_ID else config.ADMIN_USER_ID
    original = msg.reply_to_message
    prefix = f"Telegram message from {NAMES[peer]}:\n"
    if (original and original.from_user and original.from_user.id == context.bot.id
            and (original.text or "").startswith(prefix)):
        body = text
    else:
        if re.search(r"\b(?:email|gmail|e-mail)\b", text, re.I):
            return False
        body = parse_message(text, peer)
        if not body:
            if re.search(r"\b(?:send|sent|resend|repeat|message)\b", text, re.I) and (
                re.search(r"\b(?:aishwarya|ishwarya|ayshorya|revanth|same message)\b", text, re.I)
            ):
                waiting = pending("peek") if uid == config.ADMIN_USER_ID else None
                status = "Your message is waiting for Aishwarya to connect." if waiting else "No message is queued."
                await msg.reply_text(f"{status} To send on Telegram, say: Tell {NAMES[peer]} followed by your message.")
                return True
            if re.match(r"(?:please )?send (?:a |the )?(?:telegram )?message to ", text, re.I):
                await msg.reply_text(f"Which Telegram contact did you mean? Try: Tell {NAMES[peer]} followed by your message.")
                return True
            return False
    if not config.is_authorized(peer):
        await msg.reply_text("This Telegram contact is unavailable.")
        return True
    outgoing = f"Telegram message from {NAMES[uid]}:\n{body}"
    if len(outgoing.encode("utf-16-le")) // 2 > 4096:
        await msg.reply_text("Please shorten the message so it fits in one Telegram message.")
        return True
    if not connection(AISHWARYA):
        if uid == config.ADMIN_USER_ID:
            previous = pending("save", body)
            status = "An earlier message is already waiting." if previous else "Your message is waiting."
            await msg.reply_text(status + " I can deliver it when Aishwarya sends ‘Connect me to Revanth’.")
        else:
            await msg.reply_text("To enable messaging, say: Connect me to Revanth")
        return True
    try:
        await deliver(context.bot, uid, peer, body)
    except TelegramError:
        await msg.reply_text("Telegram delivery could not be confirmed.")
    else:
        await msg.reply_text(f"Sent to {NAMES[peer]} on Telegram.")
    return True
