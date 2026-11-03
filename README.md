# YoBot — Autonomous AI Executive Assistant & Second Brain 🤖

[![Telegram Bot](https://img.shields.io/badge/Telegram-@Revu04__bot-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.me/Revu04_bot)
[![Python Version](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini-8E75C2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![OpenAI](https://img.shields.io/badge/AI-OpenAI%20GPT--4o--mini-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com/)
[![Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://jarvis-bot-rhuk.onrender.com/)

An asynchronous, cloud-native Telegram AI personal assistant built in Python. Powered by a dual-brain architecture (**OpenAI GPT-4o-mini** and a multi-tier **Google Gemini failover pool**), YoBot functions as a full-featured second brain for managing expenses, reading progress, recurring reminders, tasks, and daily habits with autonomous function calling.

👉 **Live Telegram Bot:** [https://telegram.me/Revu04_bot](https://telegram.me/Revu04_bot) *(or search `@Revu04_bot` on Telegram)*  
🌐 **Web Client Alternative:** [https://web.telegram.org/k/#@Revu04_bot](https://web.telegram.org/k/#@Revu04_bot)

---

## 🌟 Key Features

- **🧠 Dual-Brain AI Orchestration:** Automatically routes conversational coaching to OpenAI and seamless failover to Gemini flash models with dynamic tool execution.
- **⏰ Smart Recurring Reminders:** Natural-language interval detection (`"every 20 mins"`, `"every hour"`, `"daily"`) with 12-hour AM/PM smart resolution and automated background rescheduling.
- **💰 Expense & Financial Ledger:** Tracks spendings, calculates monthly totals, groups by category, and normalizes natural-language dates.
- **📚 Book Reading Tracker:** Logs current reading progress, pages read, completion status, and personal reading notes.
- **🛡️ Data Guardian Master Vault:** Atomic JSON snapshots of SQLite data, including habit completion history. Cloud durability requires persistent storage for both the databases and the vault.
- **📊 Google Sheets Live Cloud Sync:** Instant SQLite transactions coupled with non-blocking background synchronization to a live Google Spreadsheet dashboard accessible directly from your phone.
- **🎙️ Voice & Multimodal:** Supports voice message transcription, receipt image recognition, and Edge-TTS voice replies.
- **🔒 Multi-Tenant Privacy Isolation:** Thread-safe user session isolation via Python `contextvars`, allowing seamless sharing with friends while keeping personal records private.
- **⚡ 24/7 Cloud Resilience:** Built-in HTTP health server and self-pinger. The free deployment does not guarantee uninterrupted operation or durable local storage.

---

## 🛠️ Tech Stack

- **Language:** Python 3.13 (Asyncio)
- **Bot Framework:** `python-telegram-bot` (v20+ with JobQueue)
- **AI Models:** Google Gemini (`gemini-2.5-flash`, `gemini-3.7-flash`), OpenAI `gpt-4o-mini`
- **Database:** SQLite3 (partitioned per user) with JSON vault backup
- **Audio & TTS:** Microsoft Edge Neural TTS (`edge-tts`)
- **Hosting:** Render Cloud Web Service with automated keep-alive heartbeat

---

## 💬 How to Use YoBot on Telegram

Simply open [@Revu04_bot](https://t.me/Revu04_bot) on Telegram and start chatting naturally:

| Capability | Example Telegram Prompt |
| :--- | :--- |
| **Recurring Reminder** | *"Remind me every 20 mins to drink water"* |
| **Specific Reminder** | *"Remind me at 7:45 PM to review budget"* |
| **Stop Reminders** | *"/remind stop water"* or *"stop water reminder"* |
| **Log Expense** | *"Spent 150 on filter coffee and snacks today"* |
| **Expense Summary** | *"How much did I spend this month?"* |
| **Google Sheets Dashboard** | *"/sheets"* or *"Give me the link to my Google Sheet"* |
| **Reading Progress** | *"I read up to page 88 in The Pragmatic Programmer"* |
| **Habits & Tasks** | *"Add habit Morning Meditation"* or *"Add task Call accountant"* |
| **Live Info** | *"What is the weather in Hyderabad today?"* |

---

## 🚀 Local Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/revanthh04/JarvisBot.git
   cd JarvisBot
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Create a `.env` file in the root directory:
   ```env
   TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
   GEMINI_API_KEY="your_gemini_api_key"
   OPENAI_API_KEY="your_openai_api_key"
   ALLOWED_USER_IDS="your_telegram_user_id"
   TIMEZONE="Asia/Kolkata"
   PORT=8080
   ```

5. **Run the diagnostic verification suite:**
   ```bash
   python test_suite.py
   ```

6. **Start YoBot:**
   ```bash
   python bot.py
   ```

---

## 🧪 Testing & Verification

YoBot includes an automated 18-parameter diagnostic suite and a synthetic QA inspector agent:
```bash
python test_suite.py          # Runs all 18 subsystem tests
python qa_inspector_agent.py   # Runs live 12-parameter production audit
```

---

## 👤 Author & Links

- **Developer:** Revanth Acharya
- **GitHub:** [@revanthh04](https://github.com/revanthh04)
- **Live Bot:** [@Revu04_bot](https://t.me/Revu04_bot)


## Regression testing and storage

Run `python test_suite.py` or `python -m unittest discover -s tests -v` for the offline regression suite. It copies source files into a temporary workspace, uses synthetic records, and mocks external services. It does not run the Telegram bot or read local credentials.

The original diagnostics are available only through `python test_suite.py --live`. They modify databases and the clipboard, call paid AI services, and can create or overwrite Google Sheets. They are not the default verification path.

Access is closed by default (`OPEN_ACCESS=false`). The admin and IDs in `ALLOWED_USER_IDS` can use the bot; Gmail, Calendar, Sheets, LinkedIn, and workstation controls are admin-only. AI-provided user IDs cannot override the authenticated user. The admin's Google Sheet exports only the admin's records and is a **one-way SQLite export**, not a two-way database.

`JARVIS_DATA_DIR` optionally selects the directory containing all six SQLite files, `data_vault_backup.json`, and `sheets_config.json`. If omitted, the project directory is used as before. Before switching directories, stop the bot and copy the existing databases and vault into the new directory, then restart one bot instance. Do not point it at an empty directory expecting an automatic migration.

The checked-in Render blueprint still uses the free plan. Render documents that local files are lost on restarts, redeploys, and spin-downs, and that persistent disks require a paid service: [free service limitations](https://render.com/docs/free#local-files-lost-on-redeploy), [persistent disk setup](https://render.com/docs/disks). After provisioning a persistent mount such as `/var/data`, set `JARVIS_DATA_DIR` to that mount and migrate the existing data before starting the bot. A local vault alone is not an off-server backup.

See [BUGFIX_REPORT.md](BUGFIX_REPORT.md) for verified fixes and remaining work.
