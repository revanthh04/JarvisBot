import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/gmail.modify'
]

def main():
    creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')

    if not os.path.exists(creds_path):
        print("ERROR: credentials.json not found in project directory.")
        print("Please download credentials.json from Google Cloud Console first.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, 'w') as token:
        token.write(creds.to_json())
    print("SUCCESS: token.json generated successfully! Google services are now connected.")

if __name__ == '__main__':
    main()
