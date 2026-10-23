import os
import base64
from email.mime.text import MIMEText

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

def read_email(msg_id: str) -> str:
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    if not os.path.exists(token_path):
        return "Gmail is not linked yet."

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from bs4 import BeautifulSoup

        creds = Credentials.from_authorized_user_file(token_path)
        service = build("gmail", "v1", credentials=creds)

        m = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        snippet = m.get("snippet", "")
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        
        subject = headers.get("subject", "No Subject")
        sender = headers.get("from", "Unknown")

        return f"From: {sender}\nSubject: {subject}\n\nSnippet:\n{snippet}"
    except Exception as e:
        return f"Failed to read email {msg_id}: {e}"

def send_email(to: str, subject: str, body: str) -> str:
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    if not os.path.exists(token_path):
        return "Gmail is not linked yet."

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(token_path)
        service = build("gmail", "v1", credentials=creds)

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email successfully sent to {to} (Message ID: {sent['id']})."
    except Exception as e:
        return f"Failed to send email: {e}"
