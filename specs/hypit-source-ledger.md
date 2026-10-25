# Spec: hypit-source-ledger
Status: draft

## MUST - Functional core
### Description
Persist exact Hypit Run/Author source versions and edit intents before upstream
execution. This internal ledger does not send edits or establish caller approval.
The broker must enforce fresh app/source rights and grant/checkpoint authority.

### Requirements (EARS)
- The system shall store app/project-scoped immutable source versions with exact upstream revision, source bytes and content hashes through `source_versions`.
- The system shall persist a parameter edit intent before dispatch and reject stale source heads, changed idempotency inputs or more than 1 unresolved attempt through `edit_intent`.
- The system shall reject automatic replay of prepared or uncertain attempts and retain their original intent for inspection through `uncertain_recovery`.
- The system shall atomically store accepted or rejected upstream source observations with the attempt result and new source head through `edit_result`.
- The system shall reject a rejected edit whose source bytes changed, source-set changes, invalid revision order or modified saved history through `source_integrity`.
- The system shall return hash-only history receipts without source text or native parameter endpoints through `ledger_receipts`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: source_versions
  Given an internally approved source bundle for one app
  When `source_versions` is saved and the database is reopened
  Then exact version and source hashes persist without foreign app access
Scenario: edit_intent
  Given a current source head and a retry key
  When `edit_intent` is saved twice or races another request
  Then the same intent is returned only for identical input and at most one unresolved attempt exists
Scenario: uncertain_recovery
  Given a prepared attempt or lost response
  When `uncertain_recovery` is inspected after restart
  Then it remains inspect-only and cannot authorize another dispatch
Scenario: edit_result
  Given an unresolved edit and observed upstream result
  When `edit_result` is finalized
  Then source version, attempt outcome and head commit together
Scenario: source_integrity
  Given changed history, changed source membership or a rejected edit with different bytes
  When `source_integrity` validates the observation
  Then no new version or successful result is stored
Scenario: ledger_receipts
  Given retained source and native intent records
  When `ledger_receipts` lists history
  Then only scoped identities, revisions, outcomes and hashes are returned
```

## Authorized parameters
MAX_FILES = 32
MAX_SOURCE_BYTES = 1048576
MAX_VERSIONS = 200
MAX_ATTEMPTS = 500

## SHOULD - Integration
PREPARED means the intent is durable, not that execution happened. Both PREPARED
and UNCERTAIN block a new intent until current source is inspected. An identical
retry returns dispatch_allowed false and never re-sends. APPLIED/REJECTED are
observed source outcomes, not publication or final media approval. External source
edits require a separate conflict workflow; do not silently replace the head.
Keep private source text/native proposal bodies inside the operational database.
No public transport is added here. Use the existing transaction/automation guard.
