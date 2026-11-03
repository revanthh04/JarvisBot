import config
import os
import base64
from email.mime.text import MIMEText
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

@config.require_admin
def send_email(to: str, subject: str, body: str) -> str:
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
        message = MIMEText(body, "plain", "utf-8")
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email successfully sent to {to} (Message ID: {sent['id']})."
    except Exception as e:
        return f"Failed to send email: {e}"
