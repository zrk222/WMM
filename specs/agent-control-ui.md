# Spec: agent-control-ui
Status: draft

## MUST - Functional core
### Description
Complete human controls for the existing grant and reviewed-dispatch backend. This packet retains the full product goal; it does not waive remaining operation coverage, provider transports or full integrated acceptance.

### Requirements (EARS)
- The system shall let a freshly authenticated owner list, issue and revoke app-scoped finite agent grants with explicit lifetime, call ceiling and per-write independent review selection through `grant_controls`.
- The system shall display an issued bearer token once in a password control and clear it on dialog close, app change or review-session identity change without storing or reporting it through `secret_delivery`.
- The system shall page the actual human review API with bounded metadata, explicit counts and loading, empty and recoverable error states through `review_queue`.
- The system shall inspect the exact frozen envelope, hashes, revision, maker, expiry, result and transition history before independent human approval or cancellation through `exact_review`.
- The system shall let a distinct authenticated checker record a known outcome and evidence hash for uncertain work without enabling replay through `reconciliation`.
- The system shall reject changed app version or human identity before writes, suppress duplicate submits and discard late responses after dialog replacement or app switching through `scope_safety`.
- The system shall show brief purpose and next steps, source-specific counts and sanitized printable reports for grants, queue and exact review without exporting credentials or raw request inputs through `reports`.
- The system shall return existing agent and activity controls alongside the new controls and emit desktop and mobile keyboard, error recovery, API persistence, independent approval and PDF evidence with synthetic identities through `integration`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: grant_controls
  Given a loaded app and authenticated review session
  When `grant_controls` is exercised
  Then the exact authorized scope is retained and invalid or stale actions are rejected
Scenario: secret_delivery
  Given a loaded app and authenticated review session
  When `secret_delivery` is exercised
  Then the exact authorized scope is retained and invalid or stale actions are rejected
Scenario: review_queue
  Given a loaded app and authenticated review session
  When `review_queue` is exercised
  Then the exact authorized scope is retained and invalid or stale actions are rejected
Scenario: exact_review
  Given a loaded app and authenticated review session
  When `exact_review` is exercised
  Then the exact authorized scope is retained and invalid or stale actions are rejected
Scenario: reconciliation
  Given a loaded app and authenticated review session
  When `reconciliation` is exercised
  Then the exact authorized scope is retained and invalid or stale actions are rejected
Scenario: scope_safety
  Given a loaded app and authenticated review session
  When `scope_safety` is exercised
  Then the exact authorized scope is retained and invalid or stale actions are rejected
Scenario: reports
  Given a loaded app and authenticated review session
  When `reports` is exercised
  Then the exact authorized scope is retained and invalid or stale actions are rejected
Scenario: integration
  Given a loaded app and authenticated review session
  When `integration` is exercised
  Then the exact authorized scope is retained and invalid or stale actions are rejected
```

## SHOULD - Technical
- Reuse common CSRF, fresh identity, grant, checkpoint, modal and print services.
- Escape untrusted text; export only whitelisted operational metadata.
- Synthetic GitHub identity responses prove software behavior, not genuine human identity acceptance.
- No agent approval tool, provider publication, spend or production activation.

## Authorized parameters
PAGE_SIZE = 100
MAX_HOURS = 24
MAX_CALLS = 10000
