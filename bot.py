import os
import io
import re
import logging
import asyncio
from datetime import time
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import config
import ai_agent
import device_service
import notes_service
import habits_service
import tasks_service
import expenses_service
import weather_service
import cricket_service
import calc_service
import voice_service
import calendar_service
import gmail_service
import reminders_service
import books_service

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("JarvisBot")

# Markdown to Telegram HTML Converter for Beautiful Rich Text
def markdown_to_telegram_html(text: str) -> str:
    if not text:
        return ""

    def escape_tg(s: str) -> str:
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    code_blocks = []
    def save_code_block(match):
        code_blocks.append(escape_tg(match.group(1)))
        return f"___CODEBLOCK{len(code_blocks)-1}___"

    inline_codes = []
    def save_inline_code(match):
        inline_codes.append(escape_tg(match.group(1)))
        return f"___INLINECODE{len(inline_codes)-1}___"

    # Save code blocks
    text = re.sub(r'```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```', save_code_block, text, flags=re.DOTALL)
    text = re.sub(r'`([^`\n]+)`', save_inline_code, text)

    # Escape HTML special characters on the main text
    text = escape_tg(text)

    # Replace bold italics ***text*** -> <b><i>text</i></b>
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)

    # Replace bold **text** -> <b>\1</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # Replace italic *text* or _text_ -> <i>\1</i>
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', text)

    # Replace headers # Title -> <b>Title</b>
    text = re.sub(r'^[#]{1,6}\s*(.*)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Clean bullet points '* ' to '• '
    text = re.sub(r'^\s*[\*\-]\s+', '• ', text, flags=re.MULTILINE)

    # Remove any stray asterisks that were not closed
    text = text.replace('*', '')

    # Restore code blocks and inline codes
    for i, cb in enumerate(code_blocks):
        text = text.replace(f"___CODEBLOCK{i}___", f"<pre><code>{cb}</code></pre>")
    for i, ic in enumerate(inline_codes):
        text = text.replace(f"___INLINECODE{i}___", f"<code>{ic}</code>")

    return text.strip()

async def send_rich_reply(update: Update, text: str):
    html_text = markdown_to_telegram_html(text)
    try:
        await update.message.reply_text(html_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.warning(f"Telegram HTML parse error: {e}, sending plain clean text")
        clean = re.sub(r'<[^>]+>', '', html_text)
        await update.message.reply_text(clean)

# Lightweight HTTP Health Check Server (for 24/7 Render keep-alive)
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "service": "Jarvis AI Assistant"}')

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress health check access logs

def start_health_server(port=8080):
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check HTTP server running on port {port}")
    except Exception as e:
        logger.warning(f"Could not start health check server on port {port}: {e}")

# Security check decorator
def restricted(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not config.is_authorized(user_id):
            logger.warning(f"Unauthorized access attempt by user {user_id}")
            if update.message:
                await update.message.reply_text("⛔ Access Denied. Jarvis is restricted to authorized executive users.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# Command Handlers
@restricted
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 **JARVIS Executive AI Assistant Online**\n\n"
        "Welcome! All core subsystems are operational.\n\n"
        "**Available Commands:**\n"
        "• `/device` or `/pc` — System telemetry (CPU, RAM, Battery)\n"
        "• `/screenshot` — Capture live desktop screen\n"
        "• `/lock` — Lock computer workstation\n"
        "• `/volume [action]` — PC Volume control (mute, up, down)\n"
        "• `/clipboard [text]` — View or set PC clipboard\n"
        "• `/tasks` — Manage your to-do list\n"
        "• `/notes [query]` — Second Brain notes search\n"
        "• `/books` — Track reading list and book page progress\n"
        "• `/expenses` — View monthly expense ledger\n"
        "• `/habits` — Habit streaks and daily check-ins\n"
        "• `/weather [city]` — Live weather forecast\n"
        "• `/cricket` — Live cricket scores\n"
        "• `/convert [amt] [from] [to]` — Currency conversion\n"
        "• `/agenda` — Google Calendar upcoming meetings\n"
        "• `/briefing` — Trigger morning briefing\n"
        "• `/speak [text]` — Synthesize neural voice note\n\n"
        "💡 *You can also simply type or send voice memos in natural language!*"
    )
    await send_rich_reply(update, welcome_text)

@restricted
async def cmd_device(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = device_service.get_system_stats()
    text = (
        "🖥️ **Workstation Telemetry:**\n"
        f"• **OS:** `{stats['os']}`\n"
        f"• **CPU Load:** `{stats['cpu_percent']}`\n"
        f"• **RAM:** `{stats['ram_used']}`\n"
        f"• **Storage:** `{stats['disk_free']}`\n"
        f"• **Battery:** `{stats['battery']}`"
    )
    await send_rich_reply(update, text)

@restricted
async def cmd_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Capturing desktop screenshot...")
    try:
        shot_bytes = device_service.take_screenshot()
        await update.message.reply_photo(photo=shot_bytes, caption="🖥️ Current Desktop Screen")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to capture screenshot: {e}")

@restricted
async def cmd_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    locked = device_service.lock_workstation()
    if locked:
        await update.message.reply_text("🔒 Workstation locked successfully.")
    else:
        await update.message.reply_text("⚠️ Could not lock workstation (Non-Windows platform or permission denied).")

@restricted
async def cmd_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.args[0] if context.args else "mute"
    res = device_service.set_volume(action)
    await update.message.reply_text(f"🔊 {res}")

@restricted
async def cmd_clipboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        text = " ".join(context.args)
        res = device_service.set_clipboard(text)
        await update.message.reply_text(f"📋 {res}")
    else:
        content = device_service.get_clipboard()
        await send_rich_reply(update, f"📋 **Current Clipboard:**\n```\n{content}\n```")

@restricted
async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        task_text = " ".join(context.args)
        tasks_service.add_task(task_text)
        await send_rich_reply(update, f"✅ Added task: **{task_text}**")
    else:
        active = tasks_service.list_tasks(completed=False)
        if not active:
            await update.message.reply_text("📝 No pending tasks on your list. Add one with `/tasks Buy groceries`.")
            return
        lines = ["📝 **Pending Tasks:**"]
        for t in active:
            lines.append(f"• `[ID {t['id']}]` {t['title']}")
        lines.append("\nTip: Tell Jarvis *'Mark task 2 as completed'* to complete it.")
        await send_rich_reply(update, "\n".join(lines))

@restricted
async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        query = " ".join(context.args)
        results = notes_service.search_notes(query)
        if not results:
            await update.message.reply_text(f"🔍 No notes found matching '{query}'.")
            return
        lines = [f"🔍 **Notes matching '{query}':**"]
        for n in results:
            lines.append(f"• **{n['title']}**\n  {n['content']}\n")
        await send_rich_reply(update, "\n".join(lines))
    else:
        recent = notes_service.list_notes(limit=5)
        if not recent:
            await update.message.reply_text("🧠 Second Brain is empty. Ask Jarvis: *'Note down server password is...'*" )
            return
        lines = ["🧠 **Recent Notes:**"]
        for n in recent:
            lines.append(f"• **{n['title']}**\n  {n['content']}\n")
        await send_rich_reply(update, "\n".join(lines))

@restricted
async def cmd_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = expenses_service.get_monthly_summary()
    recent = expenses_service.get_recent_expenses(limit=5)
    
    if summary["total_expenditure"] == 0 and not recent:
        await send_rich_reply(update, "💰 **Expense Ledger**\n\nNo expenses recorded yet.\n\n• **Current Total:** ₹0.00\n• **Recent Logs:** None\n\nTo log an expense, you can tell Jarvis:\n• *Log expense ₹250 for lunch*\n• *Record an expense of ₹500 for groceries*")
        return

    lines = [
        f"💰 **Expense Ledger ({summary['month']})**",
        f"**Total Spent:** ₹{summary['total_expenditure']:,.2f}\n",
        "**By Category:**"
    ]
    for cat in summary["by_category"]:
        lines.append(f"• {cat['category']}: ₹{cat['total']:,.2f} ({cat['count']} entries)")

    if recent:
        lines.append("\n**Recent Transactions:**")
        for r in recent:
            lines.append(f"• ₹{r['amount']} — {r['category']} ({r['description']}) on {r['date']}")

    lines.append("\n📸 *Tip: Send a photo of any receipt to log it automatically!*")
    await send_rich_reply(update, "\n".join(lines))

@restricted
async def cmd_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    habits = habits_service.list_habits()
    if not habits:
        await update.message.reply_text("🌱 No habits configured yet. Tell Jarvis: *'Track habit: 30 mins reading'*.")
        return
    lines = ["🌱 **Daily Habit Tracker:**"]
    for h in habits:
        status_icon = "✅" if h["completed_today"] else "⏳"
        lines.append(f"• {status_icon} **{h['name']}** — Streak: 🔥 {h['streak']} days")
    await send_rich_reply(update, "\n".join(lines))

@restricted
async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else "Hyderabad"
    data = weather_service.get_weather(city)
    if "error" in data:
        await update.message.reply_text(f"❌ {data['error']}")
        return
    lines = [
        f"🌤️ **Weather in {data['city'].title()}**",
        f"• **Condition:** {data['condition']}",
        f"• **Temperature:** {data['temp_c']} (Feels like: {data['feels_like']})",
        f"• **Humidity:** {data['humidity']} | **Wind:** {data['wind']}\n",
        "**3-Day Forecast:**"
    ]
    for d in data.get("forecast", []):
        lines.append(f"• {d['date']}: {d['min_temp']}°C - {d['max_temp']}°C | Rain chance: {d['chance_of_rain']}")
    await send_rich_reply(update, "\n".join(lines))

@restricted
async def cmd_cricket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scores = cricket_service.get_live_cricket_scores()
    lines = ["🏏 **Live Cricket Scores:**"]
    for s in scores:
        if "match" in s:
            lines.append(f"• **{s['match']}**\n  Status: {s['status']}")
        else:
            lines.append(f"• {s.get('status')}")
    await send_rich_reply(update, "\n".join(lines))

@restricted
async def cmd_convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) >= 3:
        try:
            amt = float(args[0])
            from_c = args[1]
            to_c = args[2]
            res = calc_service.convert_currency(amt, from_c, to_c)
            await send_rich_reply(update, f"💱 {res.get('formatted', res.get('error'))}")
            return
        except ValueError:
            pass
    await send_rich_reply(update, "Usage: `/convert 100 USD INR`")

@restricted
async def cmd_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = calendar_service.get_calendar_events()
    await send_rich_reply(update, f"📅 {events}")

@restricted
async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) >= 2 and args[0].isdigit():
        mins = int(args[0])
        msg = " ".join(args[1:])
        res = reminders_service.create_reminder(message=msg, delay_minutes=mins)
        await send_rich_reply(update, f"⏰ {res['status']}")
    else:
        active = reminders_service.list_active_reminders()
        if not active:
            await send_rich_reply(update, "⏰ No active reminders. Tell Jarvis: *'Remind me in 15 minutes to call client'* or use `/remind 15 Call client`.")
        else:
            lines = ["⏰ **Active Scheduled Reminders:**"]
            for r in active:
                lines.append(f"• **{r['remind_at']}**: {r['message']}")
            await send_rich_reply(update, "\n".join(lines))

@restricted
async def cmd_books(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        books = books_service.list_books()
        if not books:
            await send_rich_reply(update, "📚 No books currently tracked.\n\nAdd one using: `/books add <Title> by <Author>`\nOr simply tell Jarvis: *'I started reading Atomic Habits'*.")
            return
        lines = ["📚 **Your Books & Reading Library:**"]
        for b in books:
            prog = f" (Page {b['current_page']}/{b['total_pages']})" if b['total_pages'] > 0 else (f" (Page {b['current_page']})" if b['current_page'] > 0 else "")
            lines.append(f"• **{b['title']}** by {b['author'] or 'Unknown'}\n  Status: {b['status']}{prog}")
        await send_rich_reply(update, "\n".join(lines))
        return

    sub = args[0].lower()
    if sub == "add":
        rest = " ".join(args[1:])
        if not rest:
            await send_rich_reply(update, "Usage: `/books add <Title> by <Author>`")
            return
        parts = rest.split(" by ")
        title = parts[0].strip()
        author = parts[1].strip() if len(parts) > 1 else ""
        res = books_service.add_book(title=title, author=author)
        await send_rich_reply(update, f"📚 {res.get('status_message', 'Book added.')}")
    elif sub in ["progress", "page", "update"]:
        if len(args) < 3:
            await send_rich_reply(update, "Usage: `/books progress <Title> <page_number>`")
            return
        page_str = args[-1]
        title_str = " ".join(args[1:-1])
        try:
            page_num = int(page_str)
            res = books_service.update_book_progress(title=title_str, current_page=page_num)
            await send_rich_reply(update, f"📚 {res.get('status_message', res.get('error', 'Progress updated.'))}")
        except ValueError:
            await send_rich_reply(update, "Invalid page number. Usage: `/books progress <Title> <page_number>`")
    elif sub == "completed":
        books = books_service.list_books(status="Completed")
        if not books:
            await send_rich_reply(update, "📚 No completed books yet.")
            return
        lines = ["🏆 **Completed Books:**"]
        for b in books:
            lines.append(f"• **{b['title']}** by {b['author'] or 'Unknown'}")
        await send_rich_reply(update, "\n".join(lines))
    else:
        query = " ".join(args)
        results = books_service.search_books(query)
        if not results:
            await send_rich_reply(update, f"📚 No books found matching '{query}'.")
            return
        lines = [f"📚 **Search results for '{query}':**"]
        for b in results:
            lines.append(f"• **{b['title']}** by {b['author'] or 'Unknown'} ({b['status']})")
        await send_rich_reply(update, "\n".join(lines))

@restricted
async def cmd_speak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else "Hello Revanth, Jarvis is at your service."
    audio_path = await voice_service.text_to_speech(text)
    try:
        with open(audio_path, "rb") as voice_file:
            await update.message.reply_voice(voice=voice_file)
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)

@restricted
async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_briefing_to_user(context, update.effective_user.id)

async def send_briefing_to_user(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    weather = weather_service.get_weather("Hyderabad")
    w_line = f"🌤️ {weather.get('condition', 'Clear')} at {weather.get('temp_c', '')} in Hyderabad."
    
    tasks = tasks_service.list_tasks(completed=False)
    task_str = f"You have {len(tasks)} pending tasks." if tasks else "No pending tasks."

    briefing_prompt = f"Give a brisk, sharp, motivating executive morning briefing to Revanth. Weather today: {w_line}. Tasks: {task_str}."
    response = ai_agent.query_agent(briefing_prompt)

    try:
        html_msg = markdown_to_telegram_html(f"🌅 **Executive Morning Briefing**\n\n{response}")
        await context.bot.send_message(chat_id=user_id, text=html_msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to send briefing: {e}")

async def check_reminders_job(context: ContextTypes.DEFAULT_TYPE):
    due = reminders_service.get_due_reminders()
    for rem in due:
        reminders_service.mark_reminder_triggered(rem["id"])
        msg = f"⏰ <b>REMINDER FOR REVANTH SIR</b>\n\n• {rem['message']}"
        try:
            await context.bot.send_message(chat_id=rem["user_id"], text=msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send reminder {rem['id']}: {e}")

# Scheduled Jobs
async def scheduled_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    for uid in config.ALLOWED_USER_IDS:
        await send_briefing_to_user(context, uid)

async def scheduled_evening_habits(context: ContextTypes.DEFAULT_TYPE):
    habits = habits_service.list_habits()
    uncompleted = [h['name'] for h in habits if not h['completed_today']]
    for uid in config.ALLOWED_USER_IDS:
        if uncompleted:
            msg = f"🌙 **Evening Habit Check-In**\n\nYou still have pending habits today:\n" + "\n".join([f"• {h}" for h in uncompleted]) + "\n\nReply 'I did [habit]' to log your streak!"
        else:
            msg = "🌙 **Evening Habit Check-In**\n\nOutstanding work! All your daily habits are marked completed! 🔥"
        try:
            html_msg = markdown_to_telegram_html(msg)
            await context.bot.send_message(chat_id=uid, text=html_msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send evening habit check-in: {e}")

# Natural Language Text Handler
@restricted
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    reply = ai_agent.query_agent(user_msg)
    await send_rich_reply(update, reply)

# Voice Note Handler (Transcribe -> Reason -> Speak back)
@restricted
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
    
    voice = update.message.voice or update.message.audio
    file = await context.bot.get_file(voice.file_id)
    
    bio = io.BytesIO()
    await file.download_to_memory(bio)
    audio_data = bio.getvalue()

    try:
        reply_text = ai_agent.analyze_audio(audio_data)
        
        reply_audio = await voice_service.text_to_speech(reply_text)
        try:
            with open(reply_audio, "rb") as v_out:
                await update.message.reply_voice(voice=v_out, caption=f"🗣️ {reply_text[:200]}")
        finally:
            if os.path.exists(reply_audio):
                os.remove(reply_audio)
    except Exception as e:
        await update.message.reply_text(f"Jarvis voice error: {e}")

# Photo Handler (Receipt parsing / Visual queries)
@restricted
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    
    bio = io.BytesIO()
    await file.download_to_memory(bio)
    photo_bytes = bio.getvalue()

    caption = update.message.caption or ""
    if "receipt" in caption.lower() or "bill" in caption.lower() or "expense" in caption.lower():
        res = ai_agent.parse_receipt_image(photo_bytes)
        await send_rich_reply(update, res.get("message", "Processed receipt."))
    else:
        query = caption if caption else "Analyze this image and describe what it contains."
        res = ai_agent.analyze_image(photo_bytes, query)
        await send_rich_reply(update, res)

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not configured in .env file.")
        return

    port = int(os.environ.get("PORT", 8080))
    start_health_server(port)

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler(["device", "pc"], cmd_device))
    app.add_handler(CommandHandler("screenshot", cmd_screenshot))
    app.add_handler(CommandHandler("lock", cmd_lock))
    app.add_handler(CommandHandler("volume", cmd_volume))
    app.add_handler(CommandHandler("clipboard", cmd_clipboard))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("books", cmd_books))
    app.add_handler(CommandHandler("expenses", cmd_expenses))
    app.add_handler(CommandHandler("habits", cmd_habits))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("cricket", cmd_cricket))
    app.add_handler(CommandHandler("convert", cmd_convert))
    app.add_handler(CommandHandler("agenda", cmd_agenda))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("speak", cmd_speak))
    app.add_handler(CommandHandler("briefing", cmd_briefing))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Scheduled Jobs
    job_queue = app.job_queue
    if job_queue:
        tz = config.get_tz()
        job_queue.run_daily(scheduled_morning_briefing, time(hour=8, minute=0, tzinfo=tz))
        job_queue.run_daily(scheduled_evening_habits, time(hour=21, minute=0, tzinfo=tz))
        job_queue.run_repeating(check_reminders_job, interval=15, first=5)
        logger.info("Daily proactive scheduled jobs & dynamic reminder engine registered.")

    print("==================================================")
    print(" JARVIS Executive Assistant is active & polling! ")
    print("==================================================")
    
    app.run_polling()

if __name__ == "__main__":
    main()
