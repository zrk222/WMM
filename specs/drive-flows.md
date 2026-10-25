# Spec: drive-flows
Status: implementation; full Drive account and media workflow remains incomplete
Parent: specs/drive-media-workflow.md T3

## MUST - Functional core
### Requirements (EARS)
- The system shall store `drive_pending` only after exact owner setup fields confirm the selected app manifest and prior connection revision, protecting the Desktop client and fresh verifier in the existing bound Vault with a 600 seconds consent lifetime and at most8 active flows per app.
- The system shall reject `drive_claim` unless the exact Drive-specific random state identifies one unexpired pending consent with a 600 seconds lifetime on its original loopback port and app revision, atomically transitioning to EXCHANGING before any token operation and refusing replay or concurrent second claims.
- The system shall reject `drive_guard` when the selected app, prior connection revision, consent expiry, listener port or protected context binding changes before or after an external step, preserving the currently connected account and returning no client secret or verifier in status responses.
- The system shall store `drive_stop` cancellation or expiry as a terminal flow state before retiring its protected candidate, winning against an in-flight callback, retaining recoverable local cleanup on native failure and never disconnecting an existing account.
- The system shall return `drive_status` for 600 seconds consent flows as at most8 app-owned recent flow summaries with explicit prepared versus exchanging versus terminal status, declared per-file modification permission and WMM read-only use, a cleanup count, and no state hash, client configuration, verifier, token or native secret reference.
- The system shall reject `drive_limits` for 600 seconds consent flows beyond1000 retained app-owned flows while preserving history, checking the active8 count again in the insertion transaction and retiring a newly staged bundle when a stale or racing insertion fails.
- The system shall emit `drive_consent_proof` from actual isolated SQLite and synthetic native-storage tests covering simultaneous claims, restart, stale manifest, changed prior connection, canceled callback, expired exchange, wrong port, wrong app, failed staging within the 600 seconds consent lifetime, retained credentials and redacted status with no external provider invocation.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_pending
  Given an exact approved app and prior connection revision
  When `drive_pending` prepares official selected-file consent
  Then its protected candidate and600-second flow are saved without replacing a connection
Scenario: drive_claim
  Given a pending one-use random state
  When `drive_claim` runs concurrently twice
  Then exactly one callback acquires the exchanging flow
Scenario: drive_guard
  Given an exchanging consent candidate
  When `drive_guard` observes changed app connection port or protected binding
  Then the next step is denied and the original connection remains
Scenario: drive_stop
  Given a pending or exchanging candidate
  When `drive_stop` cancels or expires it
  Then its state is terminal before recoverable native retirement
Scenario: drive_status
  Given pending exchanging and terminal app-owned flows
  When `drive_status` is requested
  Then only bounded redacted progress and permission summaries are returned
Scenario: drive_limits
  Given active or retained flow limits reached
  When `drive_limits` attempts another insertion
  Then history is preserved and the staged candidate is retired
Scenario: drive_consent_proof
  Given isolated synthetic app and native-store boundaries
  When `drive_consent_proof` exercises state races restart and cancellation
  Then all scope and replay denials are recorded without a live Google request
```

## WON'T - Out of scope
This packet implements pending-consent lifecycle only. Token exchange, verified
account identity, explicit account confirmation/replacement, connection activation,
refresh, disconnect and selected media downloads remain required in the same
integration. Owner UI and shared CLI/MCP controls, autonomy, reports and actual
Google acceptance also remain required. No prepared consent is a connected account.
