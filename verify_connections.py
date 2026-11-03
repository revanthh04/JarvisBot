"""Read-only live integration checks. Never prints secrets or message contents."""
import json
from pathlib import Path
from dotenv import dotenv_values
import requests

def main():
    root = Path(__file__).resolve().parent
    env = dotenv_values(root / '.env')
    results = {}
    for method in ('getMe', 'getWebhookInfo'):
        try:
            response = requests.get(f"https://api.telegram.org/bot{env.get('TELEGRAM_BOT_TOKEN', '')}/{method}", timeout=20)
            data = response.json()
            results['telegram_' + method] = {'http': response.status_code, 'ok': data.get('ok')}
            if method == 'getMe' and data.get('ok'):
                results['telegram_' + method]['username'] = data['result']['username']
            if method == 'getWebhookInfo' and data.get('ok'):
                results['telegram_' + method]['webhook_configured'] = bool(data['result'].get('url'))
        except Exception as exc:
            results['telegram_' + method] = {'error_type': type(exc).__name__}
    try:
        response = requests.get('https://generativelanguage.googleapis.com/v1beta/models', headers={'x-goog-api-key': env.get('GEMINI_API_KEY', '')}, timeout=20)
        results['gemini'] = {'http': response.status_code, 'models': [m['name'] for m in response.json().get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', [])]}
    except Exception as exc:
        results['gemini'] = {'error_type': type(exc).__name__}
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import httplib2
        import google_auth_httplib2
        creds = Credentials.from_authorized_user_file(str(root / 'token.json'))
        results['google_scopes'] = creds.scopes
        if not creds.valid:
            creds.refresh(Request())
        http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=20))
        for api, version in [('gmail', 'v1'), ('calendar', 'v3'), ('sheets', 'v4')]:
            try:
                service = build(api, version, http=http, cache_discovery=False)
                if api == 'gmail':
                    service.users().getProfile(userId='me').execute()
                elif api == 'calendar':
                    service.calendarList().list(maxResults=1).execute()
                else:
                    sid = json.loads((root / 'sheets_config.json').read_text())['spreadsheet_id']
                    service.spreadsheets().get(spreadsheetId=sid, fields='spreadsheetId').execute()
                results[api] = {'ok': True}
            except Exception as exc:
                results[api] = {'ok': False, 'error_type': type(exc).__name__, 'http': getattr(getattr(exc, 'resp', None), 'status', None)}
    except Exception as exc:
        results['google_auth'] = {'error_type': type(exc).__name__}
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
