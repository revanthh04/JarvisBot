# Sheets recovery status — 6 November 2026

## Completed and verified

- Local Google authorization refreshed successfully and passed Gmail, Calendar
  and Sheets read-only checks.
- The existing Google workbook now contains the complete owner recovery schema:
  seven data tables plus revision/checksum metadata.
- Initial snapshot: 2 expenses, 1 book, 1 note, 5 reminder records, no tasks or
  habit records. This is what was available in the saved sources; it does not
  recover cloud-only records already lost before migration.
- Four historical pending local reminders were closed during initial migration
  to prevent replay. Their rows remain in the recovery data.
- A real Google API test verified duplicate revision rejection and atomic
  validation, without changing existing cells. Temporary probe ranges were removed.
- A real cloud readback and a restore into separate temporary SQLite databases
  matched the recovery checksum.

## Not active on Render yet

The public health endpoint still reports storage.enabled=false. A recovery copy
in Sheets is not the same as automatic persistence for new Telegram changes.

Before activation, sign into the existing Render dashboard, install the current
working local token as GOOGLE_TOKEN_JSON, retain the correct workbook ID, and set
SHEETS_DURABLE_STORAGE=true. Save and deploy. Verify the health response reports
enabled=true, ready=true, pending=false, then verify new writes and restart
recovery. Never enable the flag before credentials and migration are verified.

The blueprint deliberately stays false until the credentials can be installed
in the same deployment; otherwise the bot could fail closed at startup.

## Why authorization can expire

Normal Google access tokens expire frequently and should refresh automatically.
That is different from an invalid_grant response: the refresh authorization can
no longer renew access. External OAuth apps in Testing mode issue seven-day
refresh tokens for these scopes. Other causes include revocation and, for Gmail
scopes, password changes. An old Render GOOGLE_TOKEN_JSON can also differ from a
newly authorized local token.

The Cloud project is yo-bot-512509. Google Cloud is currently requesting the
owner's password before its Audience settings can be inspected. The current
publishing status is therefore not independently verified in this session.
If it is Testing, review the applicable Production publishing requirements,
then reauthorize after that change and update Render. Production removes the
Testing-specific expiry; it does not make grants impossible to revoke.

Official reference: https://developers.google.com/identity/protocols/oauth2

## Multi-user boundary

This recovery store currently covers owner records only. Aishwarya's personal
Sheets export and Google connection are separate features, and are not yet a
durable recovery backend. Do not claim her records are protected by this owner
migration. Her Google sign-in also remains dependent on the configured web
OAuth client and secure credential database described in GOOGLE_MULTIUSER_SETUP.md.
