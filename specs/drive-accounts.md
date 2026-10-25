# Spec: drive-accounts
Status: implementation; full Drive intake remains incomplete
Parent: specs/drive-media-workflow.md T3

## MUST - Functional core
### Requirements (EARS)
- The system shall return `drive_identity` only from the fixed Google Drive account-information endpoint using the current selected-file bearer token, a 15 seconds timeout, redirects disabled and duplicate-free JSON of at most 8192 bytes, retaining a stable requesting-user permission identity and safe optional name/email without exposing token values.
- The system shall store `drive_account_candidate` only after one live consent claim, one authorization-code exchange and one verified account read, rechecking original 600 seconds flow authority before and after each step and replacing only the candidate secret while retaining the working prior connection.
- The system shall return `drive_account_review` for a 600 seconds consent lifetime with the exact verified account, selected file identities, access expiry and a packet hash for explicit owner confirmation, leaving the flow AWAITING_ACCOUNT and rejecting canceled, stale or expired candidates before connection adoption.
- The system shall store `drive_adoption` only when the owner confirms the current exact review packet hash within the 600 seconds consent lifetime and before token expiry, restaging protected values with the exact resulting connection identity/version/account/selection binding and atomically committing connection adoption plus terminal flow state.
- The system shall reject `drive_account_failure` during the 600 seconds consent lifetime after changed manifest, replaced connection, cancellation, stale packet or expired access, retiring newly staged values while preserving an existing connection and exposing an unconfirmed recovery state without replaying the authorization code.
- The system shall store `drive_disconnect` only for the current exact connection identity and integer version after explicit confirmation, atomically disabling access and canceling pending consent before recoverable local secret retirement, with no provider grant revocation or deletion of imported media.
- The system shall return `drive_connection_status` with 600 seconds consent provenance as a secret-free private account/selection summary with manifest binding, connection revision and token expiry, distinguishing connected, expired, disconnected and missing setup states, with at most24 selected file identities and no claim that the user has approved reuse or publication.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_identity
  Given a synthetic selected-file bearer token
  When `drive_identity` reads the fixed account endpoint
  Then only the verified requesting account is normalized within8192 bytes
Scenario: drive_account_candidate
  Given a live app-bound pending consent
  When `drive_account_candidate` consumes one callback and reads account identity
  Then candidate credentials await review without replacing the previous account
Scenario: drive_account_review
  Given a verified candidate and original selected file identities
  When `drive_account_review` is shown
  Then exact account selection expiry and packet hash identify what will be adopted
Scenario: drive_adoption
  Given explicit confirmation of the current candidate packet
  When `drive_adoption` commits
  Then the resulting connection owns newly bound credentials and prior unused candidates are retired
Scenario: drive_account_failure
  Given failed exchange read or stale authority during adoption
  When `drive_account_failure` recovers
  Then the original connection survives and no code replay occurs
Scenario: drive_disconnect
  Given the current exact account revision
  When `drive_disconnect` confirms local removal
  Then access and pending consent stop before recoverable native cleanup
Scenario: drive_connection_status
  Given present expired disconnected or missing account setup
  When `drive_connection_status` is read
  Then the exact private state is explicit without protected fields or reuse authority
```

## Official inputs checked 2026-10-25
Google Drive about.get accepts drive.file and requires a fields projection.
https://developers.google.com/workspace/drive/api/reference/rest/v3/about/get
Google User includes permissionId, me and optional displayName/emailAddress.
https://developers.google.com/workspace/drive/api/reference/rest/v3/User

## WON'T - Out of scope
No real Google account is connected by fixtures. HTTP/UI/CLI/MCP routing, refresh
leases, selected-file downloads, managed provenance, reuse review, autonomy,
complete editing and reports remain required in the parent integration. No broad
Drive access, provider file writes, publication or production activation.
