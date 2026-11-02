# Spec: automation-agreement-ui
Status: draft

## MUST - Functional core
### Description
Unified owner-facing inspection of existing separately enforced workflow/campaign/schedule authority; this view neither replaces approval nor activates scopes.

### Requirements (EARS)
- The system shall display existing owner workflow policies, campaign scopes and scheduled batches for exact selection through `agreement_select`.
- When the owner submits a selection, the system shall display the hash-bound combined agreement without issuing authority through `agreement_read`.
- If app, version, principal or dialog changes, the system shall reject late agreement readback through `agreement_stale`.
- The system shall emit a sanitized report of identifiers, status and approved resource allowances without private copy or credentials through `agreement_report`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: agreement_select
 Given an authenticated app owner
 When `agreement_select` checks the current selection
 Then every selected family remains visible
Scenario: agreement_read
 Given an exact current selection
 When `agreement_read` checks the current selection
 Then no policy or campaign is activated
Scenario: agreement_stale
 Given a changed workspace during read
 When `agreement_stale` checks the current selection
 Then the previous response does not replace current UI
Scenario: agreement_report
 Given a displayed agreement
 When `agreement_report` checks the current selection
 Then the report contains no post copy or secrets
```

## Authorized parameters
Synthetic review fixtures use these existing saved scope values; this UI cannot set authority.
max_total_minor = 100
max_posts = 1
max_campaigns = 1
max_calls = 50
