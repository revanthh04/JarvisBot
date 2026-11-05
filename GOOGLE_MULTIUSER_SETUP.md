# Personal Google connections

The code supports Gmail, Calendar and a separate Sheets export for each approved
Telegram user. Production activation still requires the settings below. The
deployed bot explains when setup is incomplete; it never uses the owner's tokens
for another user.

## Configure Render

Create your free external PostgreSQL database, then add these environment
variables to the existing Render service. Enter secrets directly in Render;
do not paste them in Telegram, commit them, or add them to a spreadsheet.

| Variable | Value |
| --- | --- |
| `GOOGLE_ACCOUNTS_DATABASE_URL` | PostgreSQL connection string from your database provider. TLS is required by the code. |
| `GOOGLE_ACCOUNTS_ENCRYPTION_KEY` | Stable Fernet key, generated once with the command below. Keep a secure backup. |
| `GOOGLE_OAUTH_WEB_CLIENT_JSON` | JSON downloaded for a Google **Web application** OAuth client, or its Base64 encoding. The existing desktop OAuth client does not replace this. |
| `GOOGLE_OAUTH_REDIRECT_URI` | `https://jarvis-bot-rhuk.onrender.com/google/callback` |

Generate the encryption key locally:

```powershell
.\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Do not change the key after saving accounts without a credential migration:
the old key is required to decrypt existing credentials. Database backups and
the key must be stored separately. No credentials are included in the ordinary
SQLite vault or Google Sheets exports.

In Google Cloud, enable Gmail, Calendar, Sheets and Drive APIs. Create the web
OAuth client and register the exact redirect URI above. Configure the consent
screen for the scopes listed in `google_accounts.py`. In testing mode, explicitly
add each person's Google account as a test user. Google testing authorizations
expire after seven days for these scopes; complete the applicable production
publishing requirements to avoid the testing expiry. Tokens can still be revoked.

The database schema is created automatically on first use. The connection role
needs permission to create the two tables and read/write them. PostgreSQL live
connectivity and real OAuth cannot be verified until these settings exist.

## Approve a user and connect

1. Ask the user to send `/myid` to YoBot in a private chat. This command works
   before approval and only returns that person's own numeric Telegram ID.
2. Add the ID to `ALLOWED_USER_IDS` on Render, retaining existing IDs, and deploy.
   Keep `OPEN_ACCESS=false`. Aishwarya's numeric Telegram ID is still needed;
   her name or email does not identify her Telegram account securely.
3. The approved user sends `/connectgoogle` in their private YoBot chat.
4. They choose their own Google account and approve access in Google.
5. The callback shows the selected email and a confirmation command. They send
   `/confirmgoogle CODE` back in their own Telegram chat within ten minutes.
6. `/googlestatus` checks whether credentials are stored; `/emails` and `/agenda`
   use that account. Status does not claim an expired grant is healthy.
7. `/syncsheets` creates/updates their own workbook with only their records;
   `/sheets` returns its link. These are manual exports, not automatic recovery
   or two-way edits. The owner's existing Sheets storage remains separate.
8. `/disconnectgoogle` removes local credentials, clears pending connections and
   email drafts, blocks legacy fallback, and attempts Google grant revocation.
   If revocation fails, the user can also remove YoBot in Google Account security.

Sign-in links cannot be requested in groups. OAuth state and PKCE are single-use;
confirmation codes are hashed, expire, and only work for the originating Telegram
user. Tokens are encrypted with an embedded owner ID, so moving an encrypted row
to another user fails validation. Workstation and LinkedIn controls remain
owner-only. No allowlist permissions are changed by Google sign-in.

## Local verification

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use temporary SQLite files, synthetic Google credentials and mocked APIs;
they do not send email or connect a real user's Google account. Local development
can use `GOOGLE_ACCOUNTS_SQLITE` with an ignored `google-accounts-dev.db` filename.
Render explicitly refuses this ephemeral credential store. Use PostgreSQL there.
