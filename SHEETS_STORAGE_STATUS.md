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

## Active on Render

The public health endpoint now reports enabled=true, ready=true, pending=false
on revision c4316c1. Render has the verified working token and successfully
restored the owner recovery snapshot on startup. The initial cloud snapshot and
its temporary SQLite restore have been verified.

The current working local token was installed as GOOGLE_TOKEN_JSON and
SHEETS_DURABLE_STORAGE=true was verified before saving and deploying. New writes
are saved through the synchronous durable-storage hook. Guest data is excluded.

The blueprint now retains true for subsequent deployments. Startup fails closed
if the cloud recovery store cannot be read, preventing stale local snapshots
from overwriting newer cloud records.

## Why authorization can expire

Normal Google access tokens expire frequently and should refresh automatically.
That is different from an invalid_grant response: the refresh authorization can
no longer renew access. External OAuth apps in Testing mode issue seven-day
refresh tokens for these scopes. Other causes include revocation and, for Gmail
scopes, password changes. An old Render GOOGLE_TOKEN_JSON can also differ from a
newly authorized local token.

The Cloud project is yo-bot-512509. Its Audience page was inspected in the correct
personal Chrome profile and confirms External / Testing. Publishing is disabled
until its Branding configuration is complete. Review Production requirements,
then reauthorize after that change and update Render. Production removes the
Testing-specific expiry; it does not make grants impossible to revoke.

Official reference: https://developers.google.com/identity/protocols/oauth2

## Multi-user boundary

This recovery store currently covers owner records only. Aishwarya's personal
Sheets export and Google connection are separate features, and are not yet a
durable recovery backend. Do not claim her records are protected by this owner
migration. Her Google sign-in also remains dependent on the configured web
OAuth client and secure credential database described in GOOGLE_MULTIUSER_SETUP.md.
