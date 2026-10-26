# Spec: drive-import-jobs
Status: implementation; owner UI and agent routing remain incomplete
Parent: specs/drive-media-workflow.md T5 T6 T8 T9

## MUST - Functional core
### Requirements (EARS)
- The system shall store `drive_import_queue` as an idempotent private app-owned job only after current OWNER membership, exact manifest/connection/selection and native readiness checks, binding the admitted owner role version and database namespace without storing tokens, while rejecting generic public job submission for this action.
- The system shall reject `drive_import_worker` when owner role/version, app, connection, selected source, cancellation or leased attempt changes, retaining the existing60 seconds worker lease and3 attempts recovery boundary, with no provider mutation or reuse approval.
- The system shall emit `drive_import_stages` for account verification, original metadata, download, source recheck, native validation and retained original completion, retaining actual events and elapsed time with at most200 events per app-owned job read and no fabricated percentage or cost.
- The system shall return `drive_import_private` through explicit private owner reads with current role validation, at most100 recent import jobs, and sanitized results, excluding input/result/account/file data from generic public job history and rejecting generic public cancellation of these jobs.
- The system shall store `drive_import_cancel` terminal state for the exact app-owned active import before further work, stop on the next guarded provider/native operation and prevent a canceled attempt from committing original bytes or overwriting its terminal state.
- The system shall return `drive_import_recovery` for a previously committed original with the same guarded request key after an interrupted worker result, verifying original bytes and provider provenance before marking success without duplicate media or another provider download, preserving existing source reuse status.
- The system shall emit `drive_import_job_proof` from actual isolated worker/native video tests and owner role fixtures, covering queue replay, live stage reads, cancellation, role revocation, namespace mismatch, interrupted-result recovery and generic history denial without real Google access.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_import_queue
  Given an exact current owner and selected Drive source
  When `drive_import_queue` receives an identical retry key
  Then one private durable job is retained and changed input is denied
Scenario: drive_import_worker
  Given a leased import attempt
  When `drive_import_worker` observes changed owner connection or namespace
  Then work is denied before another provider read or media commit
Scenario: drive_import_stages
  Given an active import
  When `drive_import_stages` advances through actual phases
  Then owner reads show retained stage events and elapsed time without invented progress
Scenario: drive_import_private
  Given a private import with selected account and file details
  When `drive_import_private` compares owner and generic job reads
  Then only the authorized owner read exposes its source and result
Scenario: drive_import_cancel
  Given an active app-owned import
  When `drive_import_cancel` commits
  Then the next work guard stops and the terminal state cannot be overwritten
Scenario: drive_import_recovery
  Given original bytes committed before a worker result interruption
  When `drive_import_recovery` resumes the same request
  Then exact original provenance is verified and returned without redownloading or duplicating media
Scenario: drive_import_job_proof
  Given synthetic provider credentials and actual local video bytes
  When `drive_import_job_proof` exercises manual worker success and failures
  Then real job source stage cancellation and privacy outcomes are recorded
```

## WON'T - Out of scope
No UI/HTTP/CLI/MCP route, refresh lease or autonomous authority is granted by this
backend job packet. Those remain required with full editor controls and reports.
No live Google request, provider write, publication, spending or production claim.
