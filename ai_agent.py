import os
import re
import logging
import google.generativeai as genai
import openai
import config
import notes_service
import habits_service
import tasks_service
import expenses_service
import device_service
import weather_service
import search_service
import calc_service
import cricket_service
import calendar_service
import gmail_service
import reminders_service
import books_service

logger = logging.getLogger("JarvisAI")
genai.configure(api_key=config.GEMINI_API_KEY)

# Initialize OpenAI client if API key is provided
openai_client = None
if config.OPENAI_API_KEY:
    try:
        openai_client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        logger.info("OpenAI client initialized for dual-brain architecture.")
    except Exception as e:
        logger.warning(f"Could not initialize OpenAI client: {e}")

# Pool of available models in priority order for seamless quota fallback
MODELS_POOL = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash"
]

tools_list = [
    # Notes
    notes_service.add_note,
    notes_service.search_notes,
    notes_service.list_notes,
    notes_service.delete_note,
    # Habits
    habits_service.add_habit,
    habits_service.log_habit,
    habits_service.list_habits,
    # Tasks
    tasks_service.add_task,
    tasks_service.list_tasks,
    tasks_service.complete_task,
    tasks_service.delete_task,
    # Expenses
    expenses_service.log_expense,
    expenses_service.get_monthly_summary,
    expenses_service.get_recent_expenses,
    expenses_service.get_expenses_by_date,
    expenses_service.search_expenses,
    # System / Device
    device_service.get_system_stats,
    device_service.lock_workstation,
    device_service.set_volume,
    device_service.get_clipboard,
    device_service.set_clipboard,
    # Web & Utilities
    weather_service.get_weather,
    search_service.search_web,
    calc_service.convert_currency,
    calc_service.calculate_emi,
    cricket_service.get_live_cricket_scores,
    # Google Services
    calendar_service.get_calendar_events,
    calendar_service.add_calendar_event,
    gmail_service.list_emails,
    gmail_service.read_email,
    gmail_service.send_email,
    # Proactive Reminders
    reminders_service.create_reminder,
    reminders_service.list_active_reminders,
    # Books & Reading Tracker Subsystem
    books_service.add_book,
    books_service.update_book_progress,
    books_service.list_books,
    books_service.search_books
]

SYSTEM_PROMPT = """You are JARVIS, an elite executive personal AI assistant.
Your executive user is Revanth Sir. Always address him with high respect as 'Revanth Sir'.
You are loyal, efficient, hyper-precise, proactive, and completely factual.

ANTI-HALLUCINATION & FACTUAL GROUNDING PROTOCOL:
1. NEVER guess, assume, or hallucinate dates, facts, calendar events, birthdays, expenses, books, or notes.
2. CALENDAR & SCHEDULE: When asked about events, schedule, meetings, or birthdays, ALWAYS invoke `calendar_service.get_calendar_events`. Report only what is returned by the tool.
3. EXPENSES & FINANCIALS: When asked about spendings, amounts, or receipts, ALWAYS query `get_expenses_by_date` or `get_monthly_summary`. Never guess numbers.
4. REMINDERS & ALERTS: When asked to set a reminder or alarm, ALWAYS call `create_reminder`. Confirm the exact time and date.
5. NOTES & MEMORY: When asked about anything previously noted or remembered, ALWAYS query `search_notes` or `list_notes`.
6. LIVE REAL-TIME INFO: For stock prices, live news, or factual questions, ALWAYS call `search_web`.
7. CRICKET: Always invoke `get_live_cricket_scores`.
8. WEATHER: Always invoke `get_weather`.
9. BOOKS & READING TRACKER: When asked about reading progress, books, or adding a new book to read, ALWAYS invoke `books_service` tools (`add_book`, `update_book_progress`, `list_books`, `search_books`). Never guess pages or reading status.
10. If any information is not present in the database or search, clearly and respectfully tell Revanth Sir: "I searched your records, Revanth Sir, but that is not logged yet. Would you like me to record it now?" NEVER fabricate imaginary records.

ENGLISH COMMUNICATION COACHING:
1. You also serve as Revanth Sir's executive English communication coach.
2. If Revanth Sir writes with minor grammar mistakes or colloquial phrasing, understand his request first, fulfill it, and offer a gentle, high-level English tip at the end (e.g. '💡 English phrasing: ...') when helpful.
3. When asked for English practice, grammar critique, or vocabulary expansion, provide encouraging, refined executive feedback.

CRITICAL FORMATTING INSTRUCTIONS:
1. NEVER output triple asterisks '***' or quadruple asterisks.
2. Format lists with clean dots (•) or clean numbers (1., 2.).
3. Avoid markdown clutter. Keep replies neat, crisp, and executive.

DATA PRIVACY & STORAGE INSTRUCTIONS:
1. Only store notes, tasks, habits, expenses, or books when the user EXPLICITLY asks to record, note, log, or track something.
2. Never store or invent dummy/sample data. All records in the database must belong strictly to Revanth Sir.
"""

def clean_jarvis_text(text: str) -> str:
    if not text:
        return ""
    # Strip any occurrences of triple or quadruple asterisks
    text = re.sub(r'\*{3,}', '', text)
    # Convert '* **' to '• '
    text = re.sub(r'^\s*[\*\-]\s*\*\*', '• ', text, flags=re.MULTILINE)
    # Clean dangling single asterisks
    text = re.sub(r'^\s*[\*]\s+', '• ', text, flags=re.MULTILINE)
    return text.strip()

current_model_idx = 0
chat_session = None
_last_date = None

def get_current_model_name() -> str:
    global current_model_idx
    return MODELS_POOL[current_model_idx % len(MODELS_POOL)]

def get_dynamic_system_prompt() -> str:
    from datetime import datetime
    tz = config.get_tz()
    now = datetime.now(tz)
    date_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M %p")
    return SYSTEM_PROMPT + f"\nCURRENT DATE & TIME: Today is {date_str}. Current time is {time_str} IST.\nAlways use this as the accurate real-time date and time for all responses.\n"

def init_chat_session():
    global chat_session, _last_date
    from datetime import datetime
    model_name = get_current_model_name()
    model = genai.GenerativeModel(
        model_name=model_name,
        tools=tools_list,
        system_instruction=get_dynamic_system_prompt()
    )
    chat_session = model.start_chat(enable_automatic_function_calling=True)
    _last_date = datetime.now(config.get_tz()).date()
    return chat_session

init_chat_session()

def query_openai(prompt: str) -> str:
    """
    Attempts to query OpenAI ChatGPT. If API key is available and has active quota,
    returns the ChatGPT response. If quota is exhausted or an error occurs,
    gracefully returns None to allow seamless fallback to Gemini.
    """
    if not openai_client:
        return None
    try:
        sys_prompt = get_dynamic_system_prompt()
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1200
        )
        if completion and completion.choices and completion.choices[0].message:
            return clean_jarvis_text(completion.choices[0].message.content or "")
        return None
    except Exception as e:
        err_msg = str(e).lower()
        if "quota" in err_msg or "429" in err_msg or "credit_balance_exhausted" in err_msg:
            logger.info("OpenAI quota exhausted (credit balance $0). Seamlessly falling back to Gemini failover pool.")
        else:
            logger.warning(f"OpenAI error: {e}. Falling back to Gemini pool.")
        return None

def query_gemini_agent(prompt: str) -> str:
    global current_model_idx, chat_session, _last_date
    from datetime import datetime

    # Refresh chat session if date has changed (keeps date accurate across midnight)
    today = datetime.now(config.get_tz()).date()
    if _last_date is None or today != _last_date:
        chat_session = None

    attempts = 0
    max_attempts = len(MODELS_POOL)

    while attempts < max_attempts:
        try:
            if chat_session is None:
                init_chat_session()
            response = chat_session.send_message(prompt)
            return clean_jarvis_text(response.text)
        except Exception as e:
            err_str = str(e).lower()
            # If rate limit / quota exceeded (429) or model deprecated (404)
            if "quota" in err_str or "429" in err_str or "not found" in err_str or "404" in err_str or "resourceexhausted" in err_str:
                logger.warning(f"Model {get_current_model_name()} hit quota/error. Switching to next model...")
                current_model_idx = (current_model_idx + 1) % len(MODELS_POOL)
                chat_session = None  # Reinitialize with new model
                attempts += 1
                continue
            else:
                # Reset chat session on random error and try once more
                try:
                    init_chat_session()
                    response = chat_session.send_message(prompt)
                    return clean_jarvis_text(response.text)
                except Exception as e2:
                    return f"Jarvis encountered an error: {e2}"

    return "Jarvis is temporarily rate-limited across free tiers. Please try again in a few moments."

def query_agent(prompt: str) -> str:
    """
    Intelligent dual-brain router:
    - If prompt requires specific device actions, database writes, or live services, routes directly to Gemini tool caller.
    - If conversational or general English coaching, tries OpenAI ChatGPT first (if funded).
    - If OpenAI is exhausted or fails, falls back instantly to Gemini pool without user interruption.
    """
    action_keywords = [
        "expense", "spent", "spend", "remind", "weather", "cricket",
        "calendar", "event", "birthday", "bday", "book", "reading", "page",
        "task", "habit", "lock", "clipboard", "volume", "battery",
        "system stats", "screenshot", "currency", "emi", "email"
    ]
    prompt_lower = prompt.lower()
    requires_tools = any(kw in prompt_lower for kw in action_keywords)

    if not requires_tools and openai_client:
        openai_res = query_openai(prompt)
        if openai_res:
            return openai_res

    # Tool calling or seamless fallback
    return query_gemini_agent(prompt)

def detect_image_mime(data: bytes) -> str:
    if data.startswith(b'\x89PNG'):
        return 'image/png'
    elif data.startswith(b'GIF8'):
        return 'image/gif'
    elif data.startswith(b'RIFF') and b'WEBP' in data[:12]:
        return 'image/webp'
    return 'image/jpeg'

def detect_audio_mime(data: bytes) -> str:
    if data.startswith(b'OggS'):
        return 'audio/ogg'
    elif data.startswith(b'ID3') or data.startswith(b'\xff\xfb') or data.startswith(b'\xff\xf3') or data.startswith(b'\xff\xf2'):
        return 'audio/mp3'
    elif data.startswith(b'RIFF') and b'WAVE' in data[:12]:
        return 'audio/wav'
    return 'audio/ogg'

def analyze_image(image_bytes: bytes, prompt: str = "Analyze this image and describe what you see.") -> str:
    global current_model_idx
    mime = detect_image_mime(image_bytes)
    attempts = 0
    while attempts < len(MODELS_POOL):
        try:
            m_name = get_current_model_name()
            vision_model = genai.GenerativeModel(m_name)
            img_part = {"mime_type": mime, "data": image_bytes}
            response = vision_model.generate_content([prompt, img_part])
            return clean_jarvis_text(response.text)
        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "429" in err_str or "resourceexhausted" in err_str:
                current_model_idx = (current_model_idx + 1) % len(MODELS_POOL)
                attempts += 1
                continue
            return f"Image analysis failed: {e}"
    return "Image analysis temporarily unavailable due to API rate limits."

def analyze_audio(audio_bytes: bytes, prompt: str = "Listen to this audio voice note from the user and provide an intelligent, direct executive response.") -> str:
    global current_model_idx
    mime = detect_audio_mime(audio_bytes)
    attempts = 0
    while attempts < len(MODELS_POOL):
        try:
            m_name = get_current_model_name()
            audio_model = genai.GenerativeModel(m_name)
            audio_part = {"mime_type": mime, "data": audio_bytes}
            response = audio_model.generate_content([prompt, audio_part])
            return clean_jarvis_text(response.text)
        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "429" in err_str or "resourceexhausted" in err_str:
                current_model_idx = (current_model_idx + 1) % len(MODELS_POOL)
                attempts += 1
                continue
            return f"Voice processing failed: {e}"
    return "Voice processing temporarily unavailable due to API rate limits."

def parse_receipt_image(image_bytes: bytes) -> dict:
    prompt = """Analyze this receipt or bill image. Extract the following JSON details:
{
    "amount": <total number in float>,
    "category": "<Food, Groceries, Travel, Shopping, Utilities, or Other>",
    "description": "<Vendor or brief description>",
    "date": "<YYYY-MM-DD or today's date if not visible>"
}
Respond ONLY with the JSON object.
"""
    try:
        import json
        res = analyze_image(image_bytes, prompt)
        json_match = re.search(r'\{.*\}', res, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            logged = expenses_service.log_expense(
                amount=float(data.get("amount", 0.0)),
                category=data.get("category", "General"),
                description=data.get("description", "Receipt"),
                expense_date=data.get("date")
            )
            return {
                "success": True,
                "data": logged,
                "message": f"Logged expense ₹{logged['amount']} under {logged['category']} ({logged['description']})."
            }
        return {"success": False, "message": f"Could not parse receipt JSON: {res}"}
    except Exception as e:
        return {"success": False, "message": f"Error parsing receipt: {e}"}
