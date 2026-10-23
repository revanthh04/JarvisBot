import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/calendar'
]

def main():
    creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')

    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0, prompt='consent', open_browser=True)

    with open(token_path, 'w') as token:
        token.write(creds.to_json())
    print("SUCCESS: token.json generated successfully!")

if __name__ == '__main__':
    main()
