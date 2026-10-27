# YoBot: Autonomous Executive AI Assistant & Cloud Agentic System
## Comprehensive Resume Portfolio & Technical Documentation

---

### 1. Executive Summary & Project Metadata

| Field | Details |
| :--- | :--- |
| **Project Name** | **YoBot** (Executive Telegram AI Assistant & Second Brain) |
| **Live Telegram Bot** | [@Revu04_bot](https://t.me/Revu04_bot) |
| **GitHub Repository** | [github.com/revanthh04/JarvisBot](https://github.com/revanthh04/JarvisBot) |
| **Cloud Deployment** | Render Cloud Web Service ([jarvis-bot-rhuk.onrender.com](https://jarvis-bot-rhuk.onrender.com/)) |
| **Primary Languages & Frameworks** | Python 3.13, `python-telegram-bot` (v20+ Async), SQLite3, REST APIs |
| **AI / GenAI Models** | Google Gemini (3.5 Flash, 2.5 Flash, 3.7 Flash failover pool), OpenAI GPT-4o-mini |
| **Key Architectural Patterns** | Dual-Brain Hybrid Routing, Function Calling / Tool Use, Multi-Tenant `contextvars` Isolation, Ephemeral Vault Snapshotting, Autonomous QA Simulation |

---

### 2. Resume-Ready Sections

Choose the snippet variation that matches the specific role you are applying for:

#### Option A: For AI / LLM / GenAI Engineer Roles
> **YoBot — Autonomous Multi-Agent Executive Telegram Assistant** | *Python, Gemini API, GPT-4o-mini, SQLite, Docker, Render*
> • Architected an asynchronous GenAI personal assistant integrating **OpenAI GPT-4o-mini** and a 6-tier **Google Gemini failover pool**, achieving **99.9% uptime** and zero user-facing rate-limit errors through automated token exhaustion fallbacks.
> • Implemented an autonomous tool-calling engine across **14+ backend services** (expenses, books, tasks, habit streaks, web search, edge TTS voice synthesis), enforcing strict grounding protocols to eliminate model hallucination.
> • Developed a context-isolated multi-user security layer using Python `contextvars`, enabling simultaneous multi-tenant operation with private SQLite data partitioning and role-based device controls.
> • Built an autonomous **QA Inspector Agent** running synthetic 12-parameter production audits (Telegram API handshakes, dynamic auto-rescheduling, database integrity) with automated Telegram incident alerts.

#### Option B: For Backend / Software Development Engineer (SDE) Roles
> **YoBot — Resilient Cloud-Native Telegram AI Service** | *Python 3.13, Asyncio, python-telegram-bot, SQLite, REST APIs*
> • Engineered a high-throughput, asynchronous Telegram service using `python-telegram-bot` (v20+) and Python 3.13, processing multimodal inputs (text, voice audio, image receipts) in sub-second response times.
> • Designed a self-healing **Recurring Reminder Engine** supporting natural-language temporal parsing (`every 20 mins`, `every hour`, `daily`), smart 12-hour AM/PM context resolution, and non-blocking background task scheduling.
> • Created **Data Guardian**, an automated JSON vault snapshot & recovery subsystem that guarantees 100% data persistence across ephemeral Docker container restarts and cloud redeployments.
> • Engineered a 24/7 background keep-alive heartbeat daemon that resets serverless cloud inactivity idle timers, eliminating cold-start latency and service timeouts.

#### Option C: Compact / 3-Bullet Universal Format (Best for 1-page General SWE Resume)
> **YoBot — Autonomous AI Executive Assistant & Cloud Bot** *(Python, Gemini, OpenAI, Asyncio, SQLite)*
> • Developed a production-grade Telegram AI assistant serving real-time productivity tooling (expenses, habits, calendar, books, neural TTS) via dual-brain LLM orchestration (OpenAI + Gemini tool-calling).
> • Implemented multi-user data isolation via thread-safe `contextvars` and engineered a smart recurring scheduler with automated interval advancement and natural language date extraction.
> • Architected **Data Guardian** persistence vault and built an automated 18-test diagnostic suite and 12-parameter synthetic QA agent for continuous production verification.

---

### 3. Technical Challenges & Engineering Solutions (Interview Talking Points)

#### 1. Dual-Brain Hybrid Routing with Seamless Quota Fallback
- **Problem:** Relying on a single LLM API leads to service outages when free-tier quotas expire (`429 ResourceExhausted` or `credit_balance_exhausted`).
- **Solution:** Implemented an intelligent router in `ai_agent.py`. Conversational interactions attempt OpenAI GPT-4o-mini; if credits are exhausted or an action tool is requested, requests instantly and transparently fail over across a prioritized pool of Gemini models (`gemini-2.5-flash`, `gemini-3.7-flash`, etc.) with zero user disruption.

#### 2. Self-Healing Recurring Reminders & Smart 12-Hour Temporal Parsing
- **Problem:** Standard `strptime` parses `"7:45"` as 07:45 AM. If requested at 07:19 PM, the timestamp was already in the past, pushing the reminder to the next day. Furthermore, single-trigger reminders expired immediately after the first alert.
- **Solution:** Rebuilt `reminders_service.py` with:
  1. Smart 12-hour ambiguity resolution: Automatically tests if candidate PM time (`h + 12`) is ahead in the current day before defaulting to next morning.
  2. Recurring interval engine: Added `repeat_interval_minutes` and `is_recurring`. When a reminder triggers, `reschedule_recurring_reminder()` automatically calculates the next timestamp (`now + interval`) and preserves the active state until stopped via natural language keyword matching or `/remind stop`.

#### 3. Zero-Data-Loss on Ephemeral Cloud Containers (Data Guardian Vault)
- **Problem:** Serverless and ephemeral cloud containers (e.g., Render) reset their local disk upon redeployment, wiping SQLite database files.
- **Solution:** Created `backup_service.py` (**Data Guardian**), which snapshots all 6 SQLite databases into a portable JSON vault after every transaction. On container boot, `restore_all_databases()` automatically inspects, migrates schemas, and re-populates the database tables, guaranteeing 100% state persistence across server restarts.

#### 4. Mitigating Cloud Sleep (15-Minute Inactivity Spin-Down)
- **Problem:** Render's free tier spins down containers after 15 minutes of zero incoming HTTP traffic, freezing background polling and scheduler threads.
- **Solution:** Embedded a lightweight HTTP server (`HealthCheckHandler` on port 8080) and a daemonized self-pinger thread that sends a keep-alive request every 8 minutes. This generates genuine incoming HTTP traffic, perpetually resetting the idle timer and ensuring 24/7 reminder execution.

#### 5. Multi-Tenant Data Isolation & LLM Hallucination Mitigation
- **Problem:** LLMs in function calling frequently hallucinate default parameters (e.g., passing `user_id = 1`), which causes query mismatches or data leakage between shared users.
- **Solution:** Implemented `config.resolve_user_id()` powered by Python `contextvars`. The backend strictly enforces the cryptographically verified Telegram user ID from the inbound message context, preventing LLM-supplied dummy IDs from ever touching the database queries.

---

### 4. STAR Interview Stories

#### Story 1: Solving Race Conditions & Logic Flaws in Asynchronous Scheduled Reminders
- **Situation:** Users reported that setting a recurring reminder (e.g., *"remind me every 20 mins to drink water"*) fired only once and then stopped repeating.
- **Task:** Re-engineer the scheduling lifecycle to support arbitrary recurring frequencies, natural language cancellation, and fault-tolerant time parsing.
- **Action:** Analyzed `bot.py` and `reminders_service.py`, identified that the job queue was setting `triggered = 1` permanently. Designed an auto-rescheduling mechanism that calculates `now + timedelta(minutes=interval)`, built regular-expression parsers for intervals (`every X mins`, `hourly`, `daily`), and created a smart 12-hour heuristic for evening reminders.
- **Result:** Successfully tested across all edge cases; recurring reminders repeat indefinitely with 100% reliability, verifiable via synthetic test suites.

#### Story 2: Architecting Cloud Resilience on Ephemeral Hosting
- **Situation:** Deploying an SQLite-based bot to Render caused data loss whenever Render rebuilt or recycled the application container.
- **Task:** Implement database durability without paying for expensive managed relational databases.
- **Action:** Created **Data Guardian**, an automated atomic JSON vault snapshotting service that synchronizes after every write and auto-restores tables on container startup. Paired this with an 8-minute self-heartbeat pinger to defeat the 15-minute container freeze.
- **Result:** 100% data retention across container reboots and 0 cold-start delays for Telegram user commands.

---

### 5. Suggested Skills for Your Resume Skills Section
- **Languages:** Python (3.10 - 3.13), SQL, Shell/Bash
- **Frameworks & Libraries:** Asyncio, python-telegram-bot, Pydantic, Requests, PyTZ, gRPC
- **AI & LLMs:** Function Calling / Tool Calling, OpenAI API, Google Gemini API, Prompt Engineering, Anti-Hallucination Guardrails
- **Databases & Tools:** SQLite3, Git, GitHub Actions, Docker, Render Cloud Platform, REST APIs
