# Spec: drive-auth
Status: implementation; parent Drive integration remains incomplete
Parent: specs/drive-media-workflow.md T1

## MUST - Functional core
### Requirements (EARS)
- The system shall emit `drive_consent` using the fixed Google Desktop authorization endpoint, drive.file alone, SHA256 PKCE and an actual loopback port, excluding client secret and verifier from the browser URL and preserving a 10 minutes pending-flow expiry in the subsequent connection layer.
- The system shall return `drive_selection` containing from1 to24 unique opaque file identities of at most200 characters, rejecting malformed, duplicated, empty or excess selections before any provider read.
- The system shall reject `drive_callback` with duplicate query keys, malformed encoding, foreign fields, missing proof or mixed success/error fields within a 16 KiB callback bound, returning only normalized success fields or an access_denied cancellation without echoing provider error text.
- The system shall return `drive_grant` only for an explicit initial drive.file scope, Bearer tokens and an expiry from1 to86400 seconds, preserving a previously verified refresh grant when a refresh omits its scope or refresh token while rejecting any reported scope expansion.
- The system shall send `drive_exchange` only to the fixed Google token endpoint with a 15 seconds timeout, redirects disabled, strict duplicate-free JSON and an8192 bytes token payload acceptance limit, without retrying a code or exposing secret values in diagnostics.
- The system shall preserve `drive_isolation` by reusing existing Google Desktop client and PKCE validators without changing Google Play permissions, connection records, credential storage or worker execution; no Drive account becomes connected through protocol helpers alone.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_consent
  Given a synthetic Desktop client and fresh proof
  When `drive_consent` is prepared
  Then only selected-file consent reaches the fixed browser destination without client secret or verifier
Scenario: drive_selection
  Given selected provider file identities
  When `drive_selection` normalizes the callback
  Then one to24 distinct bounded identities are retained and invalid selections are denied
Scenario: drive_callback
  Given raw callback query data
  When `drive_callback` receives duplicates malformed encoding or mixed results
  Then no ambiguous callback reaches a token exchange
Scenario: drive_grant
  Given an initial or refreshed token response
  When `drive_grant` validates permissions and expiry
  Then only the exact selected-file permission and valid retained tokens are returned
Scenario: drive_exchange
  Given a synthetic authorization code
  When `drive_exchange` uses the transport seam
  Then the fixed request has one bounded attempt and rejected responses reveal no secret values
Scenario: drive_isolation
  Given the existing Google Play and social workflows
  When `drive_isolation` regression checks run
  Then their current permissions and lifecycle tests continue to pass
```

## WON'T - Out of scope
This atomic protocol packet does not connect a real account, persist one-use
claims, enforce pending-flow expiry, import media or expose a UI/CLI/MCP operation.
Those remain required in the parent workflow, along with protected credentials,
account replacement review, reuse approvals, full editing, autonomous execution,
telemetry, exports and actual provider acceptance. No connection-complete claim.
