import os
from datetime import datetime, timedelta

def get_calendar_events(max_results: int = 5) -> str:
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    if not os.path.exists(token_path):
        return "Google Calendar is not linked yet. (Requires setup_google.py with Google Cloud credentials)."

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import config

        creds = Credentials.from_authorized_user_file(token_path)
        service = build("calendar", "v3", credentials=creds)

        tz = config.get_tz()
        now = datetime.now(tz).isoformat()
        events_result = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return "No upcoming events found on Google Calendar."

        output = ["Upcoming Calendar Events:"]
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "No Title")
            output.append(f"• {summary} ({start})")
        return "\n".join(output)
    except Exception as e:
        return f"Calendar error: {e}"

def add_calendar_event(summary: str, start_time_str: str, duration_minutes: int = 60) -> str:
    token_path = os.path.join(os.path.dirname(__file__), "token.json")
    if not os.path.exists(token_path):
        return "Google Calendar is not linked yet."

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import config

        creds = Credentials.from_authorized_user_file(token_path)
        service = build("calendar", "v3", credentials=creds)

        tz = config.get_tz()
        # Parse or default
        start_dt = datetime.fromisoformat(start_time_str)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event = {
            "summary": summary,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": config.USER_TIMEZONE},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": config.USER_TIMEZONE},
        }

        created = service.events().insert(calendarId="primary", body=event).execute()
        return f"Event created: '{summary}' on {start_dt.strftime('%Y-%m-%d %H:%M')} (Link: {created.get('htmlLink')})"
    except Exception as e:
        return f"Failed to add calendar event: {e}"
