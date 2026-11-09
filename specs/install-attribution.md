# Spec: install-attribution

Status: draft

## MUST - Functional core
### Description
Ingest an exact install export from a measurement partner (MMP) and key it by
the campaign token used on the post link. The result is descriptive: how many
supplied installs are attributed, unattributed, suppressed or unknown for that
campaign token, with explicit source coverage. It is not a rate, lift, revenue or
causal claim, and it does not replace Apple SKAN/AdAttributionKit postbacks.

### Requirements (EARS)
- The system shall accept an owner-scoped install batch with exactly `source`, `campaign_token`, `request_id`, `source_receipt_sha256`, `observed_at`, `coverage` and `installs` through `install_batch`.
- The system shall require an uppercase source token, canonical UUID campaign and request identities, a lowercase source-receipt SHA-256, and an aware observation time through `install_identity`.
- The system shall accept 0 through 1000 install rows with exactly `install_id`, `state` in `ATTRIBUTED`, `UNATTRIBUTED`, `SUPPRESSED` or `UNKNOWN`, and an aware `occurred_at` not after the observation through `install_rows`.
- The system shall reject raw personal identifiers: opaque install IDs only, no email or phone-like values.
- The system shall require coverage with explicit `complete` and a nullable bounded `source_event_count`; complete coverage must state the count.
- The system shall require an exact `window` with ordered `starts_at`/`ends_at` no longer than 90 days, require the source observation at or after the window start, and reject installs outside the window.
- The system shall retain each batch atomically; an exact repeated request returns the retained batch, while a reused request identity or conflicting install identity rejects the whole batch without writes.
- The system shall keep installs app-scoped and owner-only.
- When the campaign token matches an app-scoped observational study, the system shall record that study's identity, hash and app version with the batch; otherwise it shall report `UNLINKED`, and disagreeing links shall report `MIXED`.
- The system shall report counts per state, the retained batches, and `COMPLETE`, `PARTIAL` or `NO_IMPORT` coverage, and shall not emit a rate, lift, revenue or causal decision.
- The system shall expose a workspace summary with campaign token, batch count, coverage status and study status only, and the Results page shall state `No install export yet` while no batch exists.
- The system shall accept an optional `day` of 1, 3 or 7 and count only distinct installs whose `occurred_at` is at or before each batch's window start plus that day, without double counting repeated installs; any other day is rejected.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: install_batch
  Given an owner and a campaign token used on a post
  When an exact MMP export is recorded
  Then attributed, unattributed, suppressed and unknown installs are counted separately
  And the batch is tied to that campaign token
Scenario: install_idempotence
  Given a recorded batch
  When the exact request is replayed
  Then the retained batch is returned without duplicate rows
  And a conflicting batch is rejected atomically
Scenario: install_window
  Given a declared install window and source observation time
  When an install falls outside the window or the observation precedes it
  Then the batch is rejected without writes
Scenario: install_coverage
  Given complete, partial and absent coverage
  When the report is prepared
  Then coverage is labelled explicitly
  And zero is only reported with complete coverage
Scenario: install_study_link
  Given an install batch whose campaign token is a registered observational study
  When the batch is recorded
  Then the report links that exact study hash and app version
  And an unregistered token stays UNLINKED
Scenario: install_day_aggregation
  Given installs across the first week and repeated batches
  When the report requests day 1, 3 or 7
  Then only distinct installs at or before that day are counted
  And any other day is rejected
Scenario: install_no_export
  Given no install batch for the app
  When the Results page or workspace summary is read
  Then it states that no install export exists
  And it does not show zero installs as a measured result
Scenario: install_privacy
  Given email, phone-like or raw personal values
  When the batch is validated
  Then it is rejected without writes
  And no rate or causal field is returned
```
