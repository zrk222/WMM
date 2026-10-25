# Spec: agent-workflow-operations
Status: draft

## MUST - Functional core
### Description
Extend the fixed local agent catalog to general workflow evidence, local pipeline preparation and job observation/cancellation. Reuse existing domain services and independent reviewed dispatch. Preserve all earlier operations and the full-product goal.

### Requirements (EARS)
- The system shall store versioned app-owned workflow evidence through the existing typed validators while rejecting credential connection records, hidden fields and stale or foreign edits through `evidence_operations`.
- The system shall queue only local pipeline preparation for stage 0 through 12 with an immutable app-owned request key and reject sync, render or extra job fields through `pipeline_operations`.
- The system shall return at most 100 saved jobs for the selected app and distinguish queued admission, completed preparation and external execution that was not run through `job_observation`.
- The system shall return the saved cancellation status only for active jobs in the selected app through the existing local cancellation service and preserve their durable history without claiming a running effect was stopped through `job_cancellation`.
- The system shall reject ordinary dispatch of review-required workflow writes and resume only exact independently approved requests within the grant lifetime of at most 24 hours while retaining job submission separately from job completion through `reviewed_workflow`.
- The system shall return matching saved evidence and pipeline job receipts through actual CLI and official SDK MCP clients with scoped grants, cross-app denial and no human approval tools through `client_conformance`.
- The system shall emit current grant, checkpoint and supported operation contracts through shared discovery while keeping full-domain coverage and unsupported provider effects explicitly incomplete through `current_discovery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: evidence_operations
  Given a selected app and current operation grant
  When `evidence_operations` is exercised
  Then the exact authorized local result is retained and invalid or changed scope is rejected
Scenario: pipeline_operations
  Given a selected app and current operation grant
  When `pipeline_operations` is exercised
  Then the exact authorized local result is retained and invalid or changed scope is rejected
Scenario: job_observation
  Given a selected app and current operation grant
  When `job_observation` is exercised
  Then the exact authorized local result is retained and invalid or changed scope is rejected
Scenario: job_cancellation
  Given a selected app and current operation grant
  When `job_cancellation` is exercised
  Then the exact authorized local result is retained and invalid or changed scope is rejected
Scenario: reviewed_workflow
  Given a selected app and current operation grant
  When `reviewed_workflow` is exercised
  Then the exact authorized local result is retained and invalid or changed scope is rejected
Scenario: client_conformance
  Given a selected app and current operation grant
  When `client_conformance` is exercised
  Then the exact authorized local result is retained and invalid or changed scope is rejected
Scenario: current_discovery
  Given a selected app and current operation grant
  When `current_discovery` is exercised
  Then the exact authorized local result is retained and invalid or changed scope is rejected
```

## SHOULD - Technical
- Scope and quota apply before dispatch. Review-required writes use the common immutable checkpoint engine.
- Pipeline enqueue success is not worker completion; inspect saved jobs and real outputs.
- Local evidence assertions never establish independently verified demand, provider state or rights.
- No credentials, sign-in, provider mutation, publication, spend, arbitrary HTTP or shell operations.
- Existing five unrelated setup-feedback and Google Play files remain untouched.

## Authorized parameters
MAX_STAGE = 12
MAX_JOBS = 100
HTTP_TIMEOUT_SECONDS = 15
TEST_TIMEOUT_SECONDS = 30
TEST_GRANT_CALLS = 100
PAGING_TEST_GRANT_CALLS = 200
max_calls = 100
max_calls = 200
timeout = 30
