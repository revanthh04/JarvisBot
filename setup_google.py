import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send'
]

class InterceptString(str):
    def format(self, *args, **kwargs):
        url = kwargs.get('url')
        if url:
            link_file = os.path.join(os.path.dirname(__file__), 'auth_link.txt')
            with open(link_file, 'w', encoding='utf-8') as f:
                f.write(url)
            print(f"\n==================================================", flush=True)
            print(f"GOOGLE_AUTH_URL: {url}", flush=True)
            print(f"==================================================\n", flush=True)
        return super().format(*args, **kwargs)

def main():
    creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')
    link_file = os.path.join(os.path.dirname(__file__), 'auth_link.txt')

    if os.path.exists(link_file):
        try:
            os.remove(link_file)
        except Exception:
            pass

    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    prompt_msg = InterceptString("Please visit this URL to authorize: {url}")

    print("Starting local OAuth server...", flush=True)
    creds = flow.run_local_server(
        port=0,
        prompt='consent',
        open_browser=True,
        authorization_prompt_message=prompt_msg
    )

    with open(token_path, 'w', encoding='utf-8') as token:
        token.write(creds.to_json())

    if os.path.exists(link_file):
        try:
            os.remove(link_file)
        except Exception:
            pass

    print("SUCCESS: token.json generated successfully!", flush=True)

if __name__ == '__main__':
    main()
