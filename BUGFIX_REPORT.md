# Jarvis bug-fix pass — November 3, 2026

Scope: local code audit and offline regressions. The initial checkout was clean at `263aad5`. No deployment, real email, LinkedIn publication, Telegram polling, or live Google Sheets synchronization was performed. Existing personal databases and credentials were not used for tests.

## Fixed in this pass

| Problem | Changed behavior |
| --- | --- |
| Empty allowlist admitted everyone even with open access disabled; open access defaulted to true. | Closed by default. Only the admin and explicitly allowed users are admitted unless open access is enabled deliberately. |
| Private integrations were exposed through AI tools and several slash commands. | Admin checks run at service boundaries, private commands are guarded, and guest Gemini sessions omit private tools. |
| AI-supplied `user_id` could switch to another user's records. | Personal services resolve ownership from the active authenticated context. Trusted scheduled jobs explicitly set that context. |
| Request context persisted after handlers; scheduled messages could use the admin's data for every recipient. | Context is restored after each request, including failures; briefings and habit check-ins query the recipient's data. |
| Reminder state advanced before successful delivery, and reminder text was inserted into HTML unescaped. | State advances after Telegram accepts the message; failures stay due for retry; user text is escaped. Delivery remains at-least-once: a crash after sending but before saving can cause a repeat. |
| Compact AM times were misread; missing/invalid times silently became ten-minute reminders. | Compact AM/PM and tomorrow are handled; missing, invalid, past absolute times, and invalid recurrence intervals return clarification without inserting a reminder. |
| Rescheduled recurring reminders were not saved in the vault. | Reschedules now trigger a backup. |
| Habit completion rows were absent from backups; failures could replace a good vault with incomplete data. | `habit_logs` is included; tables in the same database are read in one transaction; snapshots use serialized, atomic replacement and preserve the previous file on failure. |
| Startup merged stale deleted records back into existing databases and discarded overdue restored alerts. | Restoration only applies to databases missing at startup; existing files remain authoritative; overdue restored reminders remain pending. |
| Voice messages received a standalone model answer without invoking action tools. | Voice is transcribed first, then routed through the same authenticated agent as text. Failed transcription does not reach the action router. |
| Notes, memory queries, and ambiguous follow-ups could use the tool-free OpenAI path. | Unknown requests go to the tool engine; OpenAI is reserved for clearly conversational or English-practice inputs. |
| AI and media requests blocked the Telegram event loop. | Text, voice, image processing, scheduled briefings, and scheduled Sheets sync use worker threads. Gemini chat access is serialized. Some direct slash-command integrations still execute synchronously. |
| Habits and monthly summaries used the host's date. | They use the configured user timezone, including month boundaries. |
| Sheets could leak guest records into the admin workbook, clear data before source reads/writes succeeded, interpret notes as formulas, or create duplicate workbooks during outages. | Export is admin-only; all source reads precede writes; writes precede stale-row trimming; values use RAW mode; configured workbook failures are reported without creating another workbook. This remains a one-way export. |
| Malformed cloud-token input could overwrite working credentials. | Raw JSON/base64 is validated and installed atomically; invalid input preserves the previous token without logging its contents. |
| Gmail reading returned only the short preview. | Nested MIME text is decoded, plain text is preferred, HTML-only messages are supported, and attachments are excluded. If no body is available, the preview is explicitly labeled. |
| Invalid Calendar dates silently scheduled an event tomorrow at 10 AM. | Invalid dates or nonpositive durations return an error without creating an event. |
| The default diagnostics mutated live data, clipboard, and Sheets. | `python test_suite.py` runs isolated regression tests. Legacy diagnostics require the explicit `--live` flag. |
| Google API client dependency was missing from installation requirements. | Added `google-api-python-client`. |
| The handoff document embedded a bot token and documentation overstated cloud durability. | Token replaced with a placeholder; documentation corrected; configurable `JARVIS_DATA_DIR` added for persistent storage. |

## Validation

- Result: **33/33 regression tests passed**; AST syntax checks passed for all 25 Python files; `git diff --check` passed. The tracked personal SQLite files and vault have no changes.
- Offline regression command: `python -m unittest discover -s tests -v`.
- Tests use temporary source copies and synthetic SQLite databases; Google, Telegram, AI, and device effects are mocked where exercised.
- Coverage includes authorization, ownership, failed reminder delivery, recovery with habit logs, stale vaults, atomic-write failures, voice routing, recipient isolation, timezone boundaries, Sheets failures, token validation, MIME parsing, and invalid Calendar input.
- No claim is made that live credentials, quotas, model availability, or the deployed Render instance passed verification.

## Remaining work and operational limits

1. **Rotate the exposed Telegram bot token through BotFather**, then update local and Render secrets. Removing the value from the current document does not remove it from Git history. Repository history also tracks personal databases and a JSON vault; review repository visibility and plan a separate history/data cleanup without deleting the working data.
2. **Provision durable cloud storage and migrate existing records.** The checked-in Render configuration uses the free plan. Its filesystem is ephemeral, and persistent disks require a paid service. The code supports a mounted `JARVIS_DATA_DIR`, but no storage was purchased or deployed. Sources: [Render free-service limits](https://render.com/docs/free#local-files-lost-on-redeploy), [persistent disks](https://render.com/docs/disks). Keep separate off-server backups.
3. **Update Render's Google token and verify scopes live.** The environment-variable entry is now in the blueprint; the remote secret was not changed. Gmail send verification needs an explicitly chosen test recipient and content.
4. **Validate live model availability and retry behavior.** The configured Gemini model pool was not changed or contacted. Automatic retries after partial tool execution can still duplicate side effects; idempotency needs a separate change.
5. **Finish reminder language coverage.** This is a limited parser, not a general date parser. Compound durations, arbitrary date phrases, ambiguous bare hours, and non-IST daylight-saving transitions need further work. Daily recurrence currently uses fixed elapsed minutes.
6. **Review receipt and expense validation.** Receipt captions trigger immediate logging, and malformed/unknown amounts and dates still need stricter validation before recording.
7. **Finish workstation control verification.** Volume code still reports unsupported actions such as `unmute` as executed. Real volume/lock/clipboard effects were not invoked during this pass.
8. **Sheets has no import/reconciliation path.** Editing the workbook does not update SQLite. Converting it to two-way sync requires conflict rules; current exports overwrite changes within exported rows.
9. LinkedIn activation remains on hold. WhatsApp and Instagram remain outside scope.

Behavior change to note: requests with no usable reminder time now ask for a time instead of silently scheduling ten minutes later. Non-admin users retain their personal notes/tasks/habits/books/expenses/reminders but cannot use the admin's Google, LinkedIn, or workstation integrations.
