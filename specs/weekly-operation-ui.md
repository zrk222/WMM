# Spec: weekly-operation-ui
Status: draft

## MUST - Functional core
### Description
Use existing weekly review for owner-specific operational exceptions while keeping anonymous prerequisite checks.

### Requirements (EARS)
- The system shall pass only trusted authenticated local identity to private weekly operational reads through `owner_projection`.
- If the current principal differs from the saved response principal, the system shall reject private exception display and stale responses through `cached_privacy`.
- The system shall open only fixed monitor campaign and private-report recovery controls after current app refresh through `fixed_recovery`.
- The system shall display operational source state and next action without private payloads or invented cost changes through `exception_clarity`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: owner_projection
 Given a current local authenticated session
 When `owner_projection` reads weekly exceptions
 Then the service receives only its verified principal
Scenario: cached_privacy
 Given a saved owner response and changed identity
 When `cached_privacy` renders or completes a delayed read
 Then private cards do not appear
Scenario: fixed_recovery
 Given an exact app-scoped operational exception
 When `fixed_recovery` opens recovery
 Then only the fixed permitted local control opens after current refresh
Scenario: exception_clarity
 Given a blocked or uncertain operational source
 When `exception_clarity` renders
 Then the concrete state and next action are visible
```
