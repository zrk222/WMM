# Spec: campaign-monitor-ui
Status: draft

## MUST - Functional core
### Description
Owners review finite exact-intent monitoring and explicitly selected protective pause rules through existing monitor services.

### Requirements (EARS)
- The system shall select saved intent IDs and request hashes in the current active scope through `exact_targets`.
- The system shall present cadence, expiry, run/read/pause allowances and explicit protective conditions before hash-bound owner activation through `review_authority`.
- If app, owner, manifest or dialog changes during a request, the system shall reject stale follow-up actions through `context_binding`.
- The system shall display saved monitor states, resource usage, job observations and OFF controls without claiming fresh provider results through `monitor_progress`.
- A stopped monitor and its report shall give different next steps for expired approval, exhausted allowance, general approval or connection repair, and unconfirmed provider state; uncertainty takes priority.
- The system shall return a report containing only selected identifiers, states and resource counts without private content or credentials through `report_projection`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: exact_targets
 Given saved intents in an active paid or post scope
 When `exact_targets` prepares monitoring
 Then only selected saved IDs and request hashes are sent
Scenario: review_authority
 Given finite monitoring and optional pause choices
 When `review_authority` activates
 Then the exact returned summary hash is submitted after owner confirmation
Scenario: context_binding
 Given a changed workspace or closed dialog
 When `context_binding` returns a delayed response
 Then no stale UI or downstream request is issued
Scenario: monitor_progress
 Given existing monitor status and saved job observations
 When `monitor_progress` inspects work
 Then usage, OFF and reconciliation guidance remain visible
Scenario: report_projection
 Given raw provider and creative payloads
 When `report_projection` exports
 Then private payloads are omitted
```

## Authorized parameters
cadence_seconds = 30
cadence_seconds = 3600
max_runs = 100
max_provider_units = 160
max_pause_attempts = 20
