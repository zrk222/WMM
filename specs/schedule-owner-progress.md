# Owner-facing saved schedule progress

Separate the persistent batch switch from what the saved receipts say happened.
Verified delivery remains visible after expiry, while unfinished work shows an
expired or inactive approval. Unknown outcomes direct the owner to reconcile
before retrying, even after the batch is turned off. Read-only status must not
dispatch, renew an approval, or imply that a delivery produced growth.

Show the same explanation on opening the schedule, refreshing it, and exporting
the report. Keep raw item states available for diagnosis.

The Facebook schedule status response adds a read-only `progress` field.
Unknown effects take precedence over repair or switch state. Validated receipts
remain verified after the switch is turned off; expired and inactive approvals
stop new starts but do not prove that an in-flight action stopped. A successful
poll clears a refresh error even if the saved response did not change.

`campaign_schedule.py` owns the local projection; `campaign-execution.mjs` renders
it consistently. Verify with the schedule Python and Node regressions and the
existing keyboard-to-schedule browser flow at desktop and narrow widths.
