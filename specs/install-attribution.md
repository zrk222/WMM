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
- The system shall retain each batch atomically; an exact repeated request returns the retained batch, while a reused request identity or conflicting install identity rejects the whole batch without writes.
- The system shall keep installs app-scoped and owner-only.
- The system shall report counts per state, the retained batches, and `COMPLETE`, `PARTIAL` or `NO_IMPORT` coverage, and shall not emit a rate, lift, revenue or causal decision.

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
Scenario: install_coverage
  Given complete, partial and absent coverage
  When the report is prepared
  Then coverage is labelled explicitly
  And zero is only reported with complete coverage
Scenario: install_privacy
  Given email, phone-like or raw personal values
  When the batch is validated
  Then it is rejected without writes
  And no rate or causal field is returned
```
