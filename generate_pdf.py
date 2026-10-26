import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted, PageBreak, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#718096"))
        # Top line above footer
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(36, 36, letter[0] - 36, 36)
        
        footer_text = "AI English Coach Telegram Bot — Complete Architecture & Build Guide"
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawString(36, 24, footer_text)
        self.drawRightString(letter[0] - 36, 24, page_text)
        self.restoreState()

def build_pdf():
    pdf_filename = os.path.join(os.path.dirname(__file__), "AI_English_Coach_Telegram_Bot_Guide.pdf")
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=46
    )

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        fontName="Helvetica",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=10
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#2B6CB0"),
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        "Heading2_Custom",
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13.5,
        textColor=colors.HexColor("#2D3748"),
        spaceBefore=7,
        spaceAfter=3,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=4
    )

    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        fontName="Helvetica",
        fontSize=9,
        leading=12.5,
        textColor=colors.HexColor("#2D3748"),
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3
    )

    code_style = ParagraphStyle(
        "Code_Custom",
        fontName="Courier",
        fontSize=7.0,
        leading=8.8,
        textColor=colors.HexColor("#1A202C")
    )

    note_style = ParagraphStyle(
        "Note_Custom",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#744210")
    )

    story = []

    # ================= PAGE 1 =================
    story.append(Paragraph("AI English Coach Telegram Bot", title_style))
    story.append(Paragraph("Architecture, Step-by-Step Build Guide & Deployment Reference Manual", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2B6CB0"), spaceAfter=10))

    # Meta Table
    meta_data = [
        [
            Paragraph("<b>Author / Recipient:</b> Revanth Acharya", body_style),
            Paragraph("<b>Target Platform:</b> Telegram (Desktop & Mobile) + Windows", body_style)
        ],
        [
            Paragraph("<b>AI Core Model:</b> OpenAI GPT-4o-mini", body_style),
            Paragraph("<b>API Integration:</b> Telegram Bot API (Python v21+)", body_style)
        ],
        [
            Paragraph("<b>Primary Purpose:</b> 24/7 Grammar & Communication Coach", body_style),
            Paragraph("<b>Deployment Modes:</b> Local PC Execution & Cloud (Render)", body_style)
        ]
    ]
    t = Table(meta_data, colWidths=[265, 275])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # Section 1: Overview
    story.append(Paragraph("1. System Overview & Objective", h1_style))
    story.append(Paragraph(
        "This project establishes a direct bridge between the <b>Telegram Bot API</b> and the <b>OpenAI API</b> to deploy a personalized, 24/7 AI communication coach. "
        "Unlike generic chat bots, this assistant is specifically prompted to analyze every message you send, identify grammatical and vocabulary inaccuracies, provide brief educational explanations, and keep dialogue engaging with natural follow-up questions.",
        body_style
    ))
    story.append(Spacer(1, 4))

    # Important Note Box
    note_data = [[
        Paragraph("<b>Important Note on OpenAI Billing:</b> A standard ChatGPT Plus web subscription does not include API usage. The OpenAI API operates on a separate developer platform (<code>platform.openai.com</code>) with a pay-as-you-go credit balance. The <code>gpt-4o-mini</code> model used here is exceptionally cost-effective, typically costing less than $0.001 per conversation.", note_style)
    ]]
    t_note = Table(note_data, colWidths=[540])
    t_note.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FEFCBF")),
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#ECC94B")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_note)
    story.append(Spacer(1, 8))

    # Section 2: Setup
    story.append(Paragraph("2. Prerequisites & Credentials Setup", h1_style))

    story.append(Paragraph("Step 2.1: Telegram Bot Token via @BotFather", h2_style))
    story.append(Paragraph("1. Open Telegram on mobile or desktop and search for the official <b>@BotFather</b>.", bullet_style))
    story.append(Paragraph("2. Send <code>/newbot</code> to start the bot creation wizard.", bullet_style))
    story.append(Paragraph("3. Provide a friendly display name (e.g., <i>Revanth English Coach</i>).", bullet_style))
    story.append(Paragraph("4. Choose a unique username ending with 'bot' (e.g., <code>revanth_english_coach_bot</code>).", bullet_style))
    story.append(Paragraph("5. Copy and securely store the generated HTTP API bot token (e.g., <code>8628427747:AAG...</code>).", bullet_style))

    story.append(Paragraph("Step 2.2: OpenAI API Secret Key Setup", h2_style))
    story.append(Paragraph("1. Log into the OpenAI Developer Platform at <font color='#2B6CB0'><u>https://platform.openai.com/api-keys</u></font>.", bullet_style))
    story.append(Paragraph("2. Navigate to <b>API Keys</b> and click <b>Create new secret key</b>.", bullet_style))
    story.append(Paragraph("3. Copy the secret key (starts with <code>sk-proj-...</code>). Store it in a safe, private location.", bullet_style))
    story.append(Paragraph("4. Under <i>Settings &gt; Billing</i>, add a payment method or top up a small credit balance (e.g. $5).", bullet_style))

    story.append(Paragraph("Step 2.3: Python Environment & Dependency Installation", h2_style))
    story.append(Paragraph("Open Windows PowerShell or Command Prompt in your project directory and execute:", body_style))
    
    pip_cmd = Table([[Paragraph("<font face='Courier'>pip install openai python-telegram-bot</font>", body_style)]], colWidths=[540])
    pip_cmd.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EDF2F7")),
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(pip_cmd)

    # ================= PAGE 2 =================
    story.append(PageBreak())
    story.append(Paragraph("3. Complete Python Implementation (telegram_ai_bot.py)", h1_style))
    story.append(Paragraph(
        "Below is the complete, production-ready Python script integrating the asynchronous OpenAI client with Telegram long-polling:",
        body_style
    ))
    story.append(Spacer(1, 4))

    code_part1 = '''import os
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# Initialize OpenAI client from environment variable
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Strict system persona enforcing communicative corrections and engagement
SYSTEM_PROMPT = (
    "You are an expert personal English communication coach. "
    "Follow these strict pedagogical rules: "
    "1. Answer user questions clearly and honestly. "
    "2. Gently highlight any grammar, spelling, or vocabulary mistakes in user input. "
    "3. Briefly explain why it was incorrect and provide a natural, native alternative. "
    "4. Conclude with an engaging follow-up question to keep conversation flowing. "
    "5. Do not agree with grammatically incorrect phrasing."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Hello Revanth! I am your personal AI English Coach.\\n\\n"
        "Send me any message in English. I will reply while checking your "
        "grammar, vocabulary, and phrasing to help you become fluent!"
    )
    await update.message.reply_text(welcome_text)'''

    code_part2 = '''async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    # Indicate typing state in Telegram while AI computes
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=600
        )
        reply = response.choices[0].message.content
        await update.message.reply_text(reply[:4000])
    except Exception as e:
        await update.message.reply_text(f"Error connecting to OpenAI: {e}")

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable is not configured.")
        return

    # Build Telegram bot application
    app = Application.builder().token(token).build()

    # Register command and message dispatchers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("==================================================")
    print(" AI English Coach Telegram Bot is live & polling! ")
    print("==================================================")
    app.run_polling()

if __name__ == "__main__":
    main()'''

    t1 = Table([[Preformatted(code_part1, code_style)]], colWidths=[540])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t1)
    story.append(Spacer(1, 6))

    t2 = Table([[Preformatted(code_part2, code_style)]], colWidths=[540])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t2)

    # ================= PAGE 3 =================
    story.append(PageBreak())
    story.append(Paragraph("4. Execution & Windows PowerShell Setup", h1_style))
    story.append(Paragraph("Set your environment variables in PowerShell and launch the script:", body_style))

    ps_commands = """# 1. Set your secret API tokens in PowerShell
$env:OPENAI_API_KEY="sk-proj-YOUR_ACTUAL_OPENAI_API_KEY"
$env:TELEGRAM_BOT_TOKEN="YOUR_ACTUAL_TELEGRAM_BOT_TOKEN"

# 2. Run the bot script
python telegram_ai_bot.py"""

    ps_code_style = ParagraphStyle(
        "PSCode_Custom",
        fontName="Courier",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#FFFFFF")
    )
    ps_table = Table([[Preformatted(ps_commands, ps_code_style)]], colWidths=[540])
    ps_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#2D3748")),
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#1A202C")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(ps_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("5. Strategic Roadmap: Advanced Extensions", h1_style))
    story.append(Paragraph(
        "Once your base bot is operating, you can progressively enhance it into a full personal language laboratory:",
        body_style
    ))

    extensions = [
        ("Multi-Turn Conversation Memory", "The starter script treats each message individually. By maintaining a sliding window of previous message turns (or saving session logs to a lightweight SQLite database), your coach can track recurring mistakes across sessions and refer back to earlier discussions."),
        ("Voice Notes & Pronunciation Coaching", "Telegram allows users to record and send voice memos. By downloading the audio and transcribing it via the OpenAI Whisper API, your bot can analyze spoken speech, transcribe it, check pronunciation patterns, and reply with audio synthesized via Edge-TTS or OpenAI TTS."),
        ("Structured Visual Feedback Cards", "Instead of plain paragraphs, configure the coach to return formatted markdown cards: <b>Corrected Sentence</b>, <b>Grammar Explanation</b>, <b>Vocabulary Alternatives</b>, and <b>Discussion Prompt</b>."),
        ("Continuous 24/7 Cloud Hosting", "Deploy the application to cloud platforms such as Render.com or Railway.app so that your coach is continuously available on your smartphone around the clock without needing your laptop powered on.")
    ]

    for title, desc in extensions:
        story.append(Paragraph(f"• <b>{title}:</b> {desc}", bullet_style))
        story.append(Spacer(1, 2))

    story.append(Spacer(1, 8))

    # Summary Box
    summary_data = [[
        Paragraph("<b>Executive Summary:</b> By combining Telegram's instantaneous mobile accessibility with OpenAI's conversational intelligence, you have a private, zero-judgment language tutor always in your pocket. Start with text coaching today, and expand into voice synthesis as your fluency expands.", note_style)
    ]]
    t_summary = Table(summary_data, colWidths=[540])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EBF8FF")),
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#BEE3F8")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 6))

    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#E2E8F0"), spaceAfter=6))
    story.append(Paragraph("Confidential & Personal — Prepared for Revanth Acharya | All Systems Operational", ParagraphStyle(
        "DocFooterNote",
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        textColor=colors.HexColor("#718096"),
        alignment=1
    )))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"SUCCESS: PDF generated cleanly at {pdf_filename}")

if __name__ == "__main__":
    build_pdf()
