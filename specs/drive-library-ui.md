# Spec: drive-library-ui
Status: implementation; autonomous agent control remains required

## MUST - Functional core
### Requirements (EARS)
- The system shall return visible Drive controls in Research and Connections alongside local upload and existing video editing controls, with exact selected-app owner scope and permission explanations, identified by `drive_library_entry`.
- The system shall store Desktop client setup only through the existing protected owner route after explicit scope confirmation, expose the official Google consent link, list pending account reviews and allow exact review confirmation or cancellation, identified by `drive_library_consent`.
- The system shall store queued imports only for user-selected authorized files with frozen app and connection revisions and unique request keys, halt a batch on uncertain failure and reconcile saved job receipts before another submission, identified by `drive_library_import`.
- The system shall return live private import stage events, elapsed time, status, cancellation, disconnect and cleanup actions with 2 seconds read-only polling while the dialog remains current, clearing polling on close or app/owner/manifest changes, identified by `drive_library_progress`.
- The system shall return observed connection/import counts and saved timestamps through PDF and JSON exports without account identifiers selected file IDs tokens client JSON or private source details, identified by `drive_library_reports`.
- The system shall emit actual browser and transport evidence for setup review selection queued imports live stages cancellation uncertainty privacy and responsive keyboard controls without live Google access, identified by `drive_library_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_library_entry
  Given a selected app and current owner
  When `drive_library_entry` exercises its Drive workflow
  Then exact scoped choices and actual results are observed
Scenario: drive_library_consent
  Given a selected app and current owner
  When `drive_library_consent` exercises its Drive workflow
  Then exact scoped choices and actual results are observed
Scenario: drive_library_import
  Given a selected app and current owner
  When `drive_library_import` exercises its Drive workflow
  Then exact scoped choices and actual results are observed
Scenario: drive_library_progress
  Given a selected app and current owner
  When `drive_library_progress` exercises its Drive workflow
  Then exact scoped choices and actual results are observed
Scenario: drive_library_reports
  Given a selected app and current owner
  When `drive_library_reports` exercises its Drive workflow
  Then exact scoped choices and actual results are observed
Scenario: drive_library_proof
  Given a selected app and current owner
  When `drive_library_proof` exercises its Drive workflow
  Then exact scoped choices and actual results are observed
```

## WON'T - Out of scope
No automatic provider token refresh, live Google acceptance or autonomous agent authority is completed by this UI packet. No publication, provider write or spending.
