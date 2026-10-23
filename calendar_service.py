import os
from datetime import datetime, timedelta
import pytz

def get_calendar_events(query: str = "", max_results: int = 15) -> str:
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
        now = datetime.now(tz).isoformat()
        
        list_kwargs = {
            "calendarId": "primary",
            "timeMin": now,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime"
        }
        if query and query.strip():
            list_kwargs["q"] = query.strip()

        events_result = service.events().list(**list_kwargs).execute()

        events = events_result.get("items", [])
        if not events:
            # If nothing upcoming from now, also check if any events match query across the year
            if query and query.strip():
                past_now = (datetime.now(tz) - timedelta(days=365)).isoformat()
                events_result = service.events().list(
                    calendarId="primary",
                    timeMin=past_now,
                    q=query.strip(),
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime"
                ).execute()
                events = events_result.get("items", [])

        if not events:
            return f"No calendar events found{f' for {query}' if query else ''}."

        output = [f"📅 Upcoming Calendar Events ({len(events)}):"]
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "No Title")
            output.append(f"• {summary} ({start})")
        return "\n".join(output)
    except Exception as e:
        return f"Calendar retrieval error: {e}"

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
        
        # Robust parsing of start_time_str
        start_time_clean = start_time_str.strip().replace("T", " ")
        start_dt = None
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
            try:
                dt_naive = datetime.strptime(start_time_clean, fmt)
                start_dt = tz.localize(dt_naive)
                break
            except ValueError:
                continue

        if not start_dt:
            try:
                start_dt = datetime.fromisoformat(start_time_str)
                if start_dt.tzinfo is None:
                    start_dt = tz.localize(start_dt)
            except Exception:
                # Default to tomorrow at 10 AM if unparseable
                now = datetime.now(tz)
                start_dt = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)

        end_dt = start_dt + timedelta(minutes=duration_minutes)

        event = {
            "summary": summary,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": config.USER_TIMEZONE},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": config.USER_TIMEZONE},
        }

        created = service.events().insert(calendarId="primary", body=event).execute()
        return f"Event created: '{summary}' on {start_dt.strftime('%A, %b %d, %Y at %I:%M %p')} (Link: {created.get('htmlLink')})"
    except Exception as e:
        return f"Failed to add calendar event: {e}"
