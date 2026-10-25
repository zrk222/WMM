# Spec: drive-secrets
Status: implementation; full Drive connection workflow remains incomplete
Parent: specs/drive-media-workflow.md T2

## MUST - Functional core
### Requirements (EARS)
- The system shall reject `drive_names` outside the selected existing app, database-location namespace, canonical secret reference and closed Drive field list, preventing an imported snapshot or another app from selecting a native credential address.
- The system shall store `drive_fields` as separate current-user protected values using the existing Vault, requiring an exact 64-character binding hash and printable ASCII values of at most 2048 bytes per field, without a plaintext fallback or secret payload in SQLite or workspace exports.
- The system shall record `drive_staging` retirement metadata before writing native fields, with a 300 seconds grace interval, retiring partially written bundles on failure and retaining opaque recovery metadata when native deletion fails.
- The system shall reject `drive_activation` outside a transaction or after the 300 seconds staging interval, verify required fields and the expected binding, and serialize attachment against cleanup while protecting active connection and pending flow references.
- The system shall reject `drive_retirement` of any currently referenced connection or pending consent bundle, preserving active credentials even when their reference is queued for cleanup, and allowing removal only after detachment or a terminal flow state.
- The system shall return `drive_cleanup` results after examining at most20 eligible app-owned bundles, retaining failed removals for the next explicit cleanup attempt and declaring that local deletion performs no provider revocation.
- The system shall emit a `drive_proof` receipt through synthetic schema, isolation, failure and recovery tests plus a disposable actual Windows Vault round trip with separate access and refresh fields each containing 2048 bytes of ASCII, verifying cleanup of every created native value and leaving real user credentials untouched.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_names
  Given a secret reference from another app or database location
  When `drive_names` derives its protected address
  Then it cannot load the original scoped secret
Scenario: drive_fields
  Given selected supported fields and an exact binding hash
  When `drive_fields` persists the bundle
  Then each value is protected separately and excluded from SQLite and workspace exports
Scenario: drive_staging
  Given a native write interrupted after one field
  When `drive_staging` recovers
  Then the partial bundle is removed or its retirement reference remains queued
Scenario: drive_activation
  Given a staged bound bundle
  When `drive_activation` receives an expired stage missing fields or a foreign binding
  Then attachment is rejected without exposing credential values
Scenario: drive_retirement
  Given a queued secret still referenced by a live connection or pending flow
  When `drive_retirement` runs
  Then the credential is preserved until its owner detaches it
Scenario: drive_cleanup
  Given more than20 eligible app-owned retirement references
  When `drive_cleanup` runs once
  Then remaining references stay queued without touching another app or provider
Scenario: drive_proof
  Given an isolated synthetic app and real native protected storage
  When `drive_proof` stores reads and retires long token fields
  Then exact values are recovered and every created native value is removed
```

## Architecture
Use the existing Vault, database-location namespace, isolated Store fixtures,
field-split staging and retirement pattern from social_secrets. Add private Drive
flow/connection/retirement tables through idempotent database initialization.
Secret fields are client_id, client_secret, verifier, access_token, refresh_token
and binding. The connection layer must derive binding from its exact app/flow,
account, selected scope and setup revision; a caller-provided hash grants nothing.

## WON'T - Out of scope
This packet does not onboard an account, process a callback, activate a connection,
read Drive files, expose UI/CLI/MCP access or implement autonomy. The full parent
workflow remains required. Existing Windows Vault behavior is retained;
cross-platform protected storage and its OS-specific acceptance remain required.
Native proof uses disposable synthetic values and does not access real credentials.
