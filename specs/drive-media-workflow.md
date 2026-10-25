# Spec: drive-media-workflow
Status: requirements; implementation and acceptance incomplete
Parent: specs/media-discovery-revision.md and the active WMM upgrade goal

## MUST - Functional core
### Requirements (EARS)
- The system shall return optional `drive_setup` for the selected WMM app with Desktop OAuth client onboarding, protected credential storage, connection scope and expiry summaries, cancellation and disconnect; local upload shall remain usable without a Drive connection.
- The system shall emit `drive_picker` through the default system browser using the official Google authorization endpoint, drive.file alone, consent, trigger_onepick=true, SHA256 PKCE, a one-use state expiring in 10 minutes and the actual loopback listener port, accepting at most 24 selected video files and never accepting an agent-supplied authorization endpoint or broad Drive scope.
- The system shall validate `drive_callback` against the live app, setup revision, pending state, expiry and original verifier before exchanging a code once, reject duplicate query keys and foreign or reused state, and preserve an existing verified connection when a replacement fails or is canceled.
- The system shall perform `drive_import` through fixed Google Drive read endpoints for an owner-selected file identity, verify current downloadable blob metadata and selected account binding before and after a bounded download, reject redirects or changed source versions, and retain original bytes, SHA256 and provider provenance through the existing managed-media validator with a 64 MiB size bound and 60 seconds video bound.
- The system shall reject `drive_reuse` without separate review for each imported video of at most 60 seconds, preserving app isolation, versioned reuse permission, original Drive selection provenance and current revocation checks before editing, queueing, execution and artifact access; a Drive grant shall not imply publication or adaptation permission.
- The system shall store shared user and agent `drive_edit` workflows for choosing imported clips and UGC, saving source-bound project revisions, ordering and trimming clips, setting supported transitions and sound levels, previewing, stitching and exporting through the existing media editor before Hypit execution, with unsupported controls remaining explicitly incomplete until implemented.
- The system shall reject out-of-scope autonomous `drive_delegate` operations to an explicitly approved app, connected source library, selected files, actions, limits and expiry, requiring tested credentials and current reuse rights for source clips of at most 60 seconds, pausing on missing setup, expired authority, revocation, changed source or cancellation, and retaining publication and spending approval boundaries.
- The system shall report `drive_progress` through UI, CLI and MCP with current import, validation, edit, render and verification stages, selected clip counts, selected and used durations, elapsed time, failures and retries for render jobs capped at 180 seconds, explicit unknown cost values and source-bound PDF and data exports, with actionable recovery and duplicate-job prevention.
- The system shall prove `drive_acceptance` with two distinct synthetic audio clips of 2 seconds each imported through the provider seam and rendered in user-selected order through owner UI, CLI, official MCP and bounded autonomous paths, verifying decoded picture, sound, timing, hashes, desktop and mobile operation, keyboard focus, cancellation, stale approval and revoked or foreign sources; authenticated Google acceptance shall be recorded separately from fixtures.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_setup
  Given an app with no connected Drive credentials
  When `drive_setup` is opened
  Then setup requirements are summarized and local upload remains available
Scenario: drive_picker
  Given a current owner-approved Desktop client
  When `drive_picker` starts
  Then the system browser opens the fixed selected-file flow with one declared scope and fresh proof
Scenario: drive_callback
  Given a pending app-bound selection
  When `drive_callback` receives repeated or foreign callback fields
  Then exchange is denied without replacing an existing connection
Scenario: drive_import
  Given an authorized selected video blob
  When `drive_import` downloads the exact file
  Then original bytes and source metadata are verified and source changes are rejected
Scenario: drive_reuse
  Given an imported source with no current adaptation permission
  When `drive_reuse` is checked before rendering
  Then the workflow requests separate owner review
Scenario: drive_edit
  Given two imported owner-reviewed clips
  When `drive_edit` saves and renders selected settings
  Then decoded output matches the exact source-bound project revision
Scenario: drive_delegate
  Given a bounded autonomous grant and onboarded credentials
  When `drive_delegate` observes revocation or expiry
  Then execution pauses and reports the required recovery
Scenario: drive_progress
  Given an active import and render job
  When `drive_progress` is read through each supported control surface
  Then stage information and exported source-bound values agree
Scenario: drive_acceptance
  Given actual synthetic imported audio clips and isolated fixture accounts
  When `drive_acceptance` exercises manual and autonomous production
  Then picture sound timing scope denial and recovery are recorded separately from real Google acceptance
```

## Architecture and delivery sequence
Follow existing play_auth/play_connections and social_flows/social_secrets patterns.
Do not introduce a second credential, OAuth, permission or job architecture. Keep
secrets outside SQLite payloads, agent responses, URLs returned to agents and logs.
The Drive connection and imported media remain separate: disconnect stops further
provider reads; local-source reuse decisions remain explicit and inspectable.
A different Drive account requires an explicit replacement review before activation.
No change may weaken the main UI Content Security Policy to load a Picker widget.

The complete integration requires onboarding and HTTP callback routing, protected
connection lifecycle, bounded download and managed-source mapping, owner UI,
shared CLI/MCP catalog operations, autonomous policy and worker telemetry, reports
and end-to-end evidence. A parser, token exchange or metadata-only button does
not satisfy the integration. Each packet has a source-hash-bound CF workflow
audit; UI packets also require Prestige, Nanna and rendered acceptance.

## Official design inputs checked 2026-10-25
Google desktop Picker: https://developers.google.com/workspace/drive/picker/guides/desktop-mobile-picker
Google scope descriptions: https://developers.google.com/workspace/drive/api/guides/api-specific-auth
Google Desktop OAuth: https://developers.google.com/identity/protocols/oauth2/native-app

Google documents selected-file Picker consent and loopback Desktop OAuth. The
chosen drive.file permission is per-file but includes modification rights; the UI
must explain that grant accurately while WMM implements provider reads only.
The file-selection callback is input to verification, not proof of reuse rights.
No provider access, credentials, paid API, publication or production activation
is performed by this requirements packet. Cross-platform protected storage,
full editing controls and every prior goal requirement remain required.

## WON'T - Out of scope
No broad Drive browsing or automatic access to all files; no remote-URL downloader,
provider file writes, credential exposure, automatic publication, ad spending,
privacy claim based only on fixtures, or substitution of this plan for execution.
