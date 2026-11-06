"""Public OAuth app information. Never includes account data or credentials."""
from html import escape

ABOUT = """YoBot is a personal assistant for approved Telegram users. It helps
with notes, expenses, tasks, habits, books and reminders. Optional Google
connections support Gmail, Calendar and Google Sheets. Google access is used
only for the account that grants it. Availability and account connection depend
on the hosting service and Google authorization."""

PRIVACY = """YoBot privacy information
Updated: 6 November 2026

What the assistant processes
YoBot processes Telegram user IDs, messages, voice transcripts, images and the
records users ask it to manage. When Google is connected, requested features can
read relevant email or calendar content, send approved emails, create calendar
events and read or update the connected Google workbook. Users choose whether
to grant Google access through Google's consent screen.

How data is used
Messages and relevant retrieved content may be processed by Google Gemini and,
when enabled, OpenAI to answer the user's request. Data also passes through
Telegram, Render hosting and Google services as required by those features.
Their own privacy policies apply to their processing. Credentials are not
included in AI prompts or ordinary spreadsheet exports. YoBot has no advertising
or data-sale feature.

Storage and access
The application stores personal records in its databases and, where activated,
Google Sheets recovery storage. The owner recovery workbook and guest account
exports are separate. Google connection credentials are stored in deployment
configuration or the application's protected credential store; personal
credential-store entries are encrypted. Approved users can access their own
records through the bot. The application operator administers the deployment
and its storage. Connections do not grant other Telegram users access to the
owner's Gmail or workstation controls.

Your choices
You can stop using the bot and revoke its Google authorization in Google Account
security settings at any time. Where personal Google connections are configured,
/disconnectgoogle removes the bot's stored personal credentials and attempts to
revoke the grant. Revocation does not delete records already exported to Google
Sheets. To request removal of application records, contact the operator through
your existing YoBot support channel or the project issue tracker. Do not send
passwords, tokens or private records to a public issue tracker.

This page describes the implemented assistant. A configured feature may still
be unavailable until its account connection or storage setup is completed."""


def html_page(path):
    if path not in ("/about", "/privacy"):
        return None
    title = "YoBot Personal Assistant" if path == "/about" else "YoBot Privacy Information"
    body = ABOUT if path == "/about" else PRIVACY
    paragraphs = "".join("<p>" + escape(p).replace("\n", " ") + "</p>" for p in body.split("\n\n"))
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title}</title><style>body{{max-width:760px;margin:48px auto;padding:0 24px;font:17px/1.6 system-ui;color:#172536}}a{{color:#1554ad}}</style>"
            f"<main><h1>{title}</h1>{paragraphs}<p><a href='/about'>About</a> · <a href='/privacy'>Privacy</a> · "
            "<a href='https://t.me/Revu04_bot'>Open YoBot</a> · "
            "<a href='https://github.com/revanthh04/JarvisBot/issues'>Project support</a></p></main></html>").encode()
