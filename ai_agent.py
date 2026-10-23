import os
import re
import logging
import google.generativeai as genai
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

logger = logging.getLogger("JarvisAI")
genai.configure(api_key=config.GEMINI_API_KEY)

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
    reminders_service.list_active_reminders
]

SYSTEM_PROMPT = """You are JARVIS, an executive personal AI assistant.
Your executive user is Revanth Sir. Always address him with high respect as 'Revanth Sir'.
You are loyal, efficient, concise, and proactive.
You have access to a rich set of system tools (reminders, PC controls, notes, habits, tasks, expenses, weather, web search, cricket scores, finance calculations, calendar, gmail).
Always pick and run the appropriate tools when Revanth Sir asks to perform an action or retrieve dynamic data.

REMINDERS & NOTIFICATIONS:
- When Revanth Sir asks you to remind him of anything (e.g. 'remind me at 1:20 PM for lunch', 'remind me in 10 minutes to take medicine', 'set reminder for...'), ALWAYS call the `create_reminder` tool!
- Confirm clearly that you have set the reminder and will actively notify him on Telegram at that exact time.

CRITICAL FORMATTING INSTRUCTIONS:
1. NEVER output triple asterisks '***' or quadruple asterisks under any circumstances.
2. Format lists with clean dots (•) or clean numbers (1., 2.).
3. Avoid markdown clutter. Keep replies neat, crisp, and executive.

DATA PRIVACY & STORAGE INSTRUCTIONS:
1. Only store notes, tasks, habits, or expenses when the user EXPLICITLY asks to record, note, log, or track something.
2. Never store or invent dummy/sample data. All records in the database must belong strictly to the user.
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

def get_current_model_name() -> str:
    global current_model_idx
    return MODELS_POOL[current_model_idx % len(MODELS_POOL)]

def init_chat_session():
    global chat_session
    model_name = get_current_model_name()
    model = genai.GenerativeModel(
        model_name=model_name,
        tools=tools_list,
        system_instruction=SYSTEM_PROMPT
    )
    chat_session = model.start_chat(enable_automatic_function_calling=True)
    return chat_session

init_chat_session()

def query_agent(prompt: str) -> str:
    global current_model_idx, chat_session
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
