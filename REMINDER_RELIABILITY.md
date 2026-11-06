# Reminder fixes and remaining hosting limitation

The reported request "and remind me at 2pm ..." bypassed the old direct parser
because it only recognized messages beginning with "remind me". The AI could
then claim success without a tool write. Follow-up prefixes now use the same
deterministic save path, and model-routed reminder confirmations are replaced
with the actual database write receipt. A missing receipt cannot confirm
creation. A model error after a successful save returns the receipt rather than
retrying the action.

This applies to all authorized users, including Revanth and Aishwarya. Regression
tests create the exact follow-up for two identities, advance to its due time,
and verify both messages target their own Telegram chats exactly once in a
successful uninterrupted run. Failed sends remain pending for retry.

## Storage and delivery

The current free Render instance still uses ephemeral SQLite. Google Sheets
durable recovery is disabled pending Google reauthorization and migration.
The external PostgreSQL account database is also not connected. Code changes
cannot make local files persist across Render restarts or deployments. The
deployments between the reported reminder's creation and its scheduled time
could have removed it even if the model did save it. The transcript cannot prove
whether that specific row was saved before the restart.

Until durable storage exists, every new reminder confirmation warns that a
restart or deployment can erase it. A request about missed reminders reads the
authenticated user's recent history, distinguishes delivery from closure, and
does not treat missing local records as proof that a reminder was never set.

After a successful durable Sheets recovery, pending overdue reminders are kept
for catch-up delivery. Messages delayed by more than 90 seconds show their
original scheduled time. With the old ephemeral snapshot, startup still closes
historical overdue reminders to prevent repeated unwanted alerts. A paid
persistent disk installation can opt into catch-up only after setting
JARVIS_DATA_DIR to the persistent mount and JARVIS_PERSISTENT_DISK=true.

Neither SQLite nor Sheets solves free-host sleep or downtime. Even with durable
records, an offline bot cannot deliver at the scheduled minute. Delivery can
catch up after recovery; it is not an uptime guarantee. Telegram sending and
database bookkeeping are separate actions, so a crash between them can also
make delivery uncertain. No claim of exactly-once delivery is made across
crashes.

## Next required infrastructure step

Complete the external database setup or reconnect Google and migrate the durable
store before relying on important future reminders. Personal Google connections
and their PostgreSQL setup are described in GOOGLE_MULTIUSER_SETUP.md. The current
Sheets recovery implementation persists only owner records; guest reminders
need their own durable backend before restart protection can be promised.
