# Spec: goal-connection-wizard
Status: draft

## MUST - Functional core
### Description
Present outcome-specific owner connection selection and the existing authoritative read-only readiness report. No policy or grant is created.

### Requirements (EARS)
- The system shall display exact fixed goal workflows and current app-owned connection choices through `select_connections`.
- When the owner requests readiness, the system shall send only the exact selection to the existing owner readiness route through `inspect_readiness`.
- If app, manifest, principal, dialog or selected goal changes, the system shall reject late readback through `stale_readback`.
- The system shall display every selected workflow blocker and a fixed repair action through `show_blockers`.
- The system shall display readiness as preparation for scope review and shall issue no execution authority through `no_authority`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: select_connections
 Given an existing selected app and goal
 When `select_connections` checks the selected state
 Then only fixed workflow choices and current app-owned profiles appear
Scenario: inspect_readiness
 Given a current authenticated owner selection
 When `inspect_readiness` checks the selected state
 Then only the exact selection is submitted without purpose or limits
Scenario: stale_readback
 Given a replaced dialog or changed app identity
 When `stale_readback` checks the selected state
 Then late readback does not replace the current interface
Scenario: show_blockers
 Given a readiness inventory with blocked selected workflows
 When `show_blockers` checks the selected state
 Then all blockers and fixed repair actions appear
Scenario: no_authority
 Given a readiness check
 When `no_authority` checks the selected state
 Then no grant or policy or campaign is activated
```

## SHOULD - Technical
- Existing Readiness.report remains authoritative; frontend badges never establish freshness.
- Campaign scope remains separate, paid effects require exact owner approval.
- Read-only selection keeps provider credentials outside the form; no raw token inputs.
