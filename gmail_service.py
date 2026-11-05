import config
import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from html import escape
import threading
import re
from html import unescape

def _message_body(payload: dict) -> str:
    """Prefer plain text, including text nested inside multipart MIME bodies."""
    plain, html = [], []
    def visit(part):
        if part.get("filename"):
            return  # Attachments are not the email's body.
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime in ("text/plain", "text/html"):
            decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
            content_type = next((h["value"] for h in part.get("headers", [])
                                 if h.get("name", "").lower() == "content-type"), mime)
            from email.message import Message
            header = Message()
            header["content-type"] = content_type
            text = decoded.decode(header.get_content_charset() or "utf-8", errors="replace")
            (plain if mime == "text/plain" else html).append(text)
        for child in part.get("parts", []):
            visit(child)
    visit(payload)
    if plain:
        return "\n\n".join(plain)
    if html:
        from bs4 import BeautifulSoup
        return BeautifulSoup("\n\n".join(html), "html.parser").get_text("\n", strip=True)
    return ""

@config.require_admin
def list_emails(query: str = "is:unread", max_results: int = 5) -> list:
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    if not os.path.exists(token_path):
        return [{"status": "Gmail is not linked yet. (Requires setup_google.py)."}]

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(token_path)
        service = build("gmail", "v1", credentials=creds)

        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = results.get("messages", [])

        if not messages:
            return [{"status": f"No messages found for query: '{query}'"}]

        email_list = []
        for msg in messages:
            m = service.users().messages().get(userId="me", id=msg["id"], format="metadata").execute()
            headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
            email_list.append({
                "id": msg["id"],
                "subject": headers.get("subject", "(No Subject)"),
                "from": headers.get("from", "Unknown"),
                "date": headers.get("date", "")
            })
        return email_list
    except Exception as e:
        return [{"error": f"Gmail list error: {e}"}]

@config.require_admin
def read_email(msg_id: str) -> str:
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    if not os.path.exists(token_path):
        return "Gmail is not linked yet."

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(token_path)
        service = build("gmail", "v1", credentials=creds)

        m = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        snippet = m.get("snippet", "")
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        
        subject = headers.get("subject", "No Subject")
        sender = headers.get("from", "Unknown")

        body = _message_body(m.get("payload", {}))
        if body:
            return f"From: {sender}\nSubject: {subject}\n\n{body}"
        return f"From: {sender}\nSubject: {subject}\n\nPreview (full body unavailable):\n{unescape(snippet)}"
    except Exception as e:
        return f"Failed to read email {msg_id}: {e}"

_drafts = {}
_draft_lock = threading.RLock()

def resolve_recipient(value: str):
    value = value.strip()
    if re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
        return value
    import notes_service
    matches = set()
    for row in notes_service.search_notes(value):
        matches.update(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", row.get("content", "")))
    return next(iter(matches)) if len(matches) == 1 else None

def preview(draft):
    return (f"**Email preview — {draft.get('tone', 'selected tone')}**\n\n"
            f"**To:** {draft['to']}\n**Subject:** {draft['subject']}\n\n{draft['body']}\n\n"
            "Reply **send** or **send email** to send, choose another tone, or **cancel**.")

@config.require_admin
def send_email(to: str, subject: str, body: str) -> str:
    """Prepare an email draft. The user must choose tone and approve in Telegram before delivery."""
    resolved = resolve_recipient(to)
    if not resolved:
        return "I couldn't find one clear saved email address for that recipient. Please provide their email address. Nothing was sent."
    with _draft_lock:
        _drafts[config.get_current_user_id()] = {
            "to": resolved, "subject": subject, "body": body, "stage": "tone",
            "original_subject": subject, "original_body": body,
        }
    return "Email not sent. Which tone would you like: formal, informal, or warm/personal? Reply with your choice, or cancel."

def handle_email_reply(text: str, rewrite):
    """Consume only explicit draft replies; unrelated questions keep their normal route."""
    uid = config.get_current_user_id()
    if not config.is_admin(uid):
        return None
    choice = text.strip().lower().rstrip('.!')
    with _draft_lock:
        draft = _drafts.get(uid)
        if draft is None:
            return None
        if choice in ("cancel", "cancel email", "discard email"):
            del _drafts[uid]
            return "Email draft cancelled. Nothing was sent."
        if choice in ("formal", "informal", "warm", "personal", "warm/personal", "friendly"):
            try:
                source = dict(draft, subject=draft["original_subject"], body=draft["original_body"])
                revised = rewrite(source, choice)
                if not isinstance(revised, dict) or not all(isinstance(revised.get(k), str) and revised[k].strip() for k in ("subject", "body")):
                    raise ValueError("Invalid draft")
            except Exception:
                return "I couldn't format the draft just now. Nothing was sent. Please choose the tone again to retry."
            draft.update(subject=revised["subject"], body=revised["body"], stage="confirm", tone=choice)
            draft['body'] = draft['body'].replace('\\n', '\n')
            return preview(draft)
        if choice in ("send", "send email", "confirm send"):
            if draft["stage"] != "confirm":
                return "Please choose formal, informal, or warm/personal first. I'll show the draft before sending."
            del _drafts[uid]  # Consume approval before I/O; never auto-retry an uncertain send.
            result = _deliver_email(draft["to"], draft["subject"], draft["body"])
            if result.startswith("Google sign-in"):
                _drafts[uid] = draft
            return result
        if choice in ("yes", "ok", "okay"):
            return "Choose a tone first." if draft["stage"] == "tone" else "To send the previewed draft, reply **send email**."
    return None

@config.require_admin
def _deliver_email(to: str, subject: str, body: str) -> str:
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    if not os.path.exists(token_path):
        return "Gmail is not linked yet."

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(token_path)
        service = build("gmail", "v1", credentials=creds)

        # Tool arguments sometimes contain double-escaped line breaks. Decode only
        # these separators, preserving Unicode and unrelated backslash sequences.
        body = body.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(body, "plain", "utf-8"))
        paragraphs = body.split("\n\n")
        html_body = '<html><body style="font-family:Arial,sans-serif;font-size:15px;line-height:1.6">' + ''.join(
            '<p>' + escape(paragraph).replace('\n', '<br>') + '</p>' for paragraph in paragraphs
        ) + '</body></html>'
        message.attach(MIMEText(html_body, "html", "utf-8"))
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email successfully sent to {to} (Message ID: {sent['id']})."
    except Exception as e:
        if "invalid_grant" in str(e) or "expired or revoked" in str(e):
            return "Google sign-in needs reconnecting. Your email was not sent and the draft is retained. After reconnecting, reply send to retry."
        return "I couldn't confirm email delivery. Please check Sent in Gmail before trying again to avoid sending twice."
