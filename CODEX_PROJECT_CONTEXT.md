# Project Codex: Jarvis (YoBot) Executive AI Assistant

> Historical handoff. See BUGFIX_REPORT.md for the November 3, 2026 code audit, verified fixes, and limitations. Claims of working integrations below are from the handoff and were not all live-verified during the audit.

## 1. Project Overview & Identity
- **Project Name:** YoBot / Jarvis Executive Assistant
- **Target Platform:** Telegram Bot (`python-telegram-bot` v21+ with JobQueue & async polling)
- **Primary User / Admin:** Revanth Sir (`ADMIN_USER_ID = 5484600217`)
- **Default Timezone:** `Asia/Kolkata` (IST)
- **Deployment Mode:** Hybrid — runs locally via Python virtual environment (`.\venv\`) with headless VBS scripts, and 24/7 on Render cloud (`render.yaml`).
- **Core Purpose:** An autonomous, executive-tier personal AI assistant that integrates workstation telemetry, personal data storage, proactive daily briefings/reminders, Google Workspace (Calendar, Gmail, Sheets, Drive), and social integrations (LinkedIn).

---

## 2. Architecture & Tech Stack

```
                                  ┌───────────────────────────┐
                                  │   Telegram Client (User)  │
                                  └─────────────┬─────────────┘
                                                │ (Voice, Audio, Photos, Text)
                                                ▼
                                    ┌───────────────────────┐
                                    │        bot.py         │
                                    │ (Handlers & JobQueue) │
                                    └───────────┬───────────┘
                                                │
                     ┌──────────────────────────┴──────────────────────────┐
                     ▼                                                     ▼
        ┌─────────────────────────┐                           ┌─────────────────────────┐
        │       ai_agent.py       │                           │    Direct Subsystems    │
        │ Dual-Brain Router &     │                           │  (SQLite & Local APIs)  │
        │ Tool Calling Agent      │                           └────────────┬────────────┘
        └────────────┬────────────┘                                        │
                     │                                                     ├─ notes_service.py (notes.db)
     ┌───────────────┴───────────────┐                                     ├─ tasks_service.py (tasks.db)
     ▼                               ▼                                     ├─ habits_service.py (habits.db)
[Google Gemini GenAI]       [OpenAI Fallback]                              ├─ expenses_service.py (expenses.db)
(gemini-3.5-flash-lite,     (gpt-4o / gpt-4o-mini)                         ├─ books_service.py (books.db)
 gemini-3.6-flash,                                                         ├─ reminders_service.py (reminders.db)
 gemini-3.5-flash)                                                         ├─ device_service.py (psutil, pywin32)
                                                                           ├─ backup_service.py (data_vault_backup.json)
                                                                           └─ voice_service.py (edge-tts)
                     │
                     ▼
       ┌─────────────────────────────┐
       │   External Cloud Services   │
       ├─────────────────────────────┤
       │ • calendar_service.py       │
       │ • gmail_service.py          │
       │ • sheets_service.py         │
       │ • linkedin_service.py       │
       │ • weather_service.py        │
       │ • cricket_service.py        │
       │ • search_service.py         │
       └─────────────────────────────┘
```

---

## 3. Core Subsystems & File Breakdown

### A. Core Engine & Orchestration
1. **`bot.py`**:
   - Primary Telegram application listener.
   - Command routing (`/start`, `/device`, `/pc`, `/screenshot`, `/lock`, `/volume`, `/clipboard`, `/tasks`, `/notes`, `/books`, `/expenses`, `/sheets`, `/syncsheets`, `/vault`, `/habits`, `/weather`, `/cricket`, `/convert`, `/agenda`, `/emails`, `/linkedin`, `/remind`, `/speak`, `/briefing`).
   - Multimodal input processors:
     - Voice/Audio: Transcribed via Gemini, synthesized reply returned as Telegram voice note via `edge-tts`.
     - Photos: Receipt OCR & analysis via Gemini vision.
   - Proactive background JobQueue jobs:
     - 08:00 AM: Executive Morning Briefing.
     - 09:00 PM: Evening Habit Check-in.
     - Every 15 seconds: Due reminder checker.
     - Every 30 minutes: Google Sheets auto-sync.
   - Includes embedded HTTP health server (port 8080) for Render keep-alive pings.

2. **`ai_agent.py`**:
   - Modern `google-genai` SDK implementation with dynamic multi-tier fallback pool (`gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.5-flash`).
   - OpenAI fallback client.
   - Dual-brain routing: Routes actionable keywords to tool-calling agents; general English coaching/conversations to conversational engines.
   - Anti-hallucination prompt protocol enforcing strict tool usage for personal data.

3. **`config.py`**:
   - Environment variables loader (`.env`).
   - Multi-user concurrency state via `contextvars`.
   - Access control checks (`ADMIN_USER_ID`, `ALLOWED_USER_IDS`, `OPEN_ACCESS`).
   - Base64 `GOOGLE_TOKEN_JSON` decoding for zero-file cloud deployment on Render.

---

### B. Personal Memory, Productivity & Databases
All local persistent databases use SQLite3 and maintain automated backups via `backup_service.py`.

1. **`reminders_service.py`** (`reminders.db`):
   - Natural language time parser supporting relative times (`in 20 mins`), absolute times (`6:00 PM`), and recurring loops (`every 20 mins`, `every hour`, `daily`).
   - AM/PM ambiguity solver (e.g., if set at 11:00 AM for "6", targets 6:00 PM).
   - Formatted output displays absolute target and countdown (e.g. `Today at 06:00 PM (in 6h 11m)`).

2. **`expenses_service.py`** (`expenses.db`):
   - Categorized financial tracking (Food, Travel, Tech, Bills, etc.).
   - Monthly summaries, date querying, receipt parsing extraction.

3. **`notes_service.py`** (`notes.db`):
   - Second brain knowledge storage with tagging and keyword search.
   - Contact storage (contains note for girlfriend Aishwarya: `aaishwaryapatil015@gmail.com`).

4. **`tasks_service.py`** (`tasks.db`):
   - Priority-based to-do list with completion toggles and overdue alerts.

5. **`habits_service.py`** (`habits.db`):
   - Streak counters, daily completion logging, evening check-in triggers.

6. **`books_service.py`** (`books.db`):
   - Reading list tracker, page progress updater, percentage completion calculation.

7. **`backup_service.py`** (`data_vault_backup.json`):
   - Data Guardian engine: Dumps all tables into a unified JSON backup upon updates.
   - Automatically restores SQLite state on container start or system wipe.

---

### C. Google Workspace & Cloud Integrations
1. **OAuth Architecture**:
   - `credentials.json` (Google Cloud Desktop Client, Project ID `47078916243`).
   - `token.json` holds OAuth 2.0 refresh and access tokens.
   - **Scopes Granted**:
     - `https://www.googleapis.com/auth/calendar`
     - `https://www.googleapis.com/auth/spreadsheets`
     - `https://www.googleapis.com/auth/drive.file`
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/gmail.send`
   - `setup_google.py`: Flow script to re-authenticate and refresh `token.json`.

2. **`gmail_service.py`**:
   - `list_emails(query, max_results)`: Reads unread inbox messages.
   - `read_email(msg_id)`: Fetches snippet and content.
   - `send_email(to, subject, body)`: Sends emails directly via Gmail API.

3. **`calendar_service.py`**:
   - `get_calendar_events()`: Upcoming meetings, agenda, birthdays.
   - `add_calendar_event()`: Direct natural language scheduling.

4. **`sheets_service.py`**:
   - Live synchronization of all SQLite tables (Expenses, Notes, Tasks, Habits, Books) into a structured Google Sheets workbook.

---

### D. Workstation & System Telemetry (Local Windows Machine)
1. **`device_service.py`**:
   - Telemetry: CPU %, RAM %, Disk Free, Battery level.
   - Remote controls: Lock workstation (`ctypes.windll.user32.LockWorkStation()`), adjust volume, read/write clipboard.
2. **`run_jarvis_silently.vbs`**:
   - Headless background launcher for Windows using `pythonw.exe`.

---

### E. Social & External APIs
1. **`linkedin_service.py`**:
   - Profile verification via OpenID Connect `/v2/userinfo` and `/v2/me`.
   - Post publishing via UGC API `/v2/ugcPosts` and modern REST `/rest/posts`.
   - Requires `LINKEDIN_ACCESS_TOKEN` in `.env` (currently placed on hold as requested).
2. **`weather_service.py`**: Open-Meteo API wrapper.
3. **`cricket_service.py`**: Live score retrieval via free endpoints / DDGS scraping.
4. **`search_service.py`**: Web search via DuckDuckGo (`ddgs`).

---

## 4. Environment Variables (`.env`)

```env
TELEGRAM_BOT_TOKEN=<your_telegram_bot_token>
GEMINI_API_KEY=<your_google_gemini_key>
OPENAI_API_KEY=<optional_openai_key>
USER_TIMEZONE=Asia/Kolkata
ALLOWED_USER_IDS=5484600217
OPEN_ACCESS=false
GOOGLE_TOKEN_JSON=<base64_string_of_token.json_for_cloud>
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_PERSON_URN=
```

---

## 5. Current State & Pending Roadmap Items

1. **Local vs Cloud Parity**:
   - The local `token.json` has full scopes (Calendar, Sheets, Drive, Gmail Read/Write).
   - The Base64 string for `GOOGLE_TOKEN_JSON` needs to be saved on Render so the cloud instance can send emails without permission errors.
2. **Contact Memory**:
   - A note has been recorded in `notes.db` linking Aishwarya's email (`aaishwaryapatil015@gmail.com`).
3. **Reminders Clarity**:
   - Updated `reminders_service.py` with relative countdowns to prevent time misinterpretations.
4. **LinkedIn**:
   - Service is written and wired into `ai_agent.py` and `bot.py` (`/linkedin`). Awaiting LinkedIn developer token.
5. **Git Status**:
   - Remote repository: `https://github.com/revanthh04/JarvisBot.git` on branch `main`.
   - Working tree has pending modified files and new files (`linkedin_service.py`, `sheets_service.py`, `sheets_config.json`) ready to commit.
