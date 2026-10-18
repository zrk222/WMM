# Spec: source-retry
Status: approved
SpecFactor-target: 0.75–2.5

## MUST — Functional core
### Description
An operator can approve a proposed retry of failed connected-provider reads from the existing Mission Control agent-resolution dialog. Successful reads and original failure receipts remain intact. The agent selects the exact retry targets; the operator approves or declines them.

### User roles
- Local operator: reviews the proposed source reads and approves an exact retry.
- Local worker: executes only approved read jobs and retains their receipts.

### Requirements (EARS)
- The system shall return `retry_candidates` containing at most 12 latest BLOCKED, FAILED or CANCELLED app-owned source reads, excluding QUEUED, RUNNING and SUCCEEDED reads.
- The system shall enforce `max_manual_source_retries` as at most 3 explicitly approved jobs per original source read in the current collection hour, with at most 12 sources per proposal.
- When an operator approves the retry proposal, the system shall store `retry_request_key` for at most 12 fresh QUEUED read jobs bound to the current app version, policy hash, connection version and exact selected failed-job hash.
- When the same approval request is replayed, the system shall compare `original_request` and return exactly the existing retry jobs without resetting their status or attempt count.
- If the app, collection hour, connection, selected failed-job hash or latest retry changes before enqueue, the system shall reject the changed `source_hash` with an empty insertion set.
- When retry reads finish, the system shall return `retry_history` containing exactly their persisted current statuses through the collection preview and existing resolution-result dialog while preserving the original receipts.
- If at least 3 retry jobs exist for a source, the system shall return `next_collection_at` with a next-collection-window explanation and source-access alternatives without retrying automatically.
- The system shall retain `external_writes` as exactly false and zero advertising spend, and reject direct client-supplied read commands for retry execution.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Failed read recovery
  Given 1 BLOCKED source read and 1 SUCCEEDED source read
  When the operator approves the current retry proposal
  Then `retry_candidates` contains 1 source and the SUCCEEDED source is not reread
  And `retry_request_key` identifies 1 fresh QUEUED read

Scenario: Bounded explicit retry
  Given 3 retry jobs for an original source in the current collection hour
  When the operator reviews the next resolution proposal
  Then `max_manual_source_retries` prevents another read
  And `next_collection_at` names the next collection window

Scenario: Immutable request replay
  Given an approved retry request with 1 QUEUED child
  When the same approval request is replayed
  Then `original_request` returns the existing child without resetting its attempt count

Scenario: Source changed
  Given a retry proposal for a BLOCKED source
  When the selected source job or connection version changes
  Then `source_hash` rejects the request and stores zero retry jobs

Scenario: Collection bound
  Given 12 failed source reads in a collection
  When the operator approves their retry proposal
  Then at most 12 fresh read jobs are stored

Scenario: Results and authority
  Given a completed source collection
  When the operator reloads its results
  Then `retry_history` contains persisted source statuses
  And `external_writes` remains false
```

## SHOULD — Technical/structural
- Existing SQLite jobs retain source-read and retry receipts. No schema migration or operational data import is required.
- Existing resolution approval binds the exact proposal and its expiry; no new external permission or generic queue action is introduced.
- Interfaces: source_retry.preview(db, app_id, task); source_retry.execute(store, app_id, parameters, request_key).
- Recovery actions remain read-only. A fresh provider permission denial remains visible and requires another explicit approval after access is reviewed.

## SHOULD NOT — Implementation details
- The feature does not publish campaigns, modify provider records, spend money, create credentials or verify campaign readiness.
- The feature does not reinterpret original failures as successes.

## Decision logic (factory candidates)
| # | if | then |
|---|----|------|
| 1 | latest read is BLOCKED, FAILED or CANCELLED and retry count is below 3 | propose exact explicit retry |
| 2 | latest read is QUEUED, RUNNING or SUCCEEDED | exclude read from retry selection |
| 3 | at least 3 retry jobs exist for a source | explain next collection window and source-access alternatives |
