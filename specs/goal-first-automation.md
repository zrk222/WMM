# Spec: goal-first-automation
Status: draft

## MUST - Functional core
### Description
Adopt the full goal-first setup and exception-driven campaign roadmap. Deliver the first bounded slice: a three-choice home over existing WMM tools, app-scoped local goal preferences and a read-only setup checklist. A local preference grants no authority.

### Requirements (EARS)
- The system shall expose Set your goal, Watch the work and Review results as three primary navigation choices through `primary_navigation`.
- The system shall display every existing view under Advanced tools through `advanced_access`.
- When an owner chooses research, creative, campaign or measurement, the system shall store only the selected fixed goal identifier under the selected app through `goal_preference`.
- If browser storage is unavailable or contains an unknown goal, the system shall return an empty choice through `storage_recovery`.
- The system shall show one next action and relevant setup links from current saved source facts through `goal_guidance`.
- The system shall display connected accounts as setup observations rather than publication or spending authority through `authority_boundary`.
- When an app changes, the system shall render only the selected app goal and source facts through `app_isolation`.
- The system shall start no provider call, approval, job or campaign when choosing a goal through `no_effect`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: primary_navigation
 Given the local workspace starts
 When `primary_navigation` checks the declared transition
 Then Set your goal and Watch the work and Review results are visible
Scenario: advanced_access
 Given an operator needs an existing tool
 When `advanced_access` checks the declared transition
 Then all existing views remain reachable
Scenario: goal_preference
 Given a selected app and a fixed goal identifier
 When `goal_preference` checks the declared transition
 Then only that fixed goal identifier is retained under the selected app
Scenario: storage_recovery
 Given missing storage or an unknown saved identifier
 When `storage_recovery` checks the declared transition
 Then the user can select a goal without a crash
Scenario: goal_guidance
 Given current selected app sources
 When `goal_guidance` checks the declared transition
 Then one primary next action and relevant setup links appear
Scenario: authority_boundary
 Given a connected account
 When `authority_boundary` checks the declared transition
 Then execution still requires its existing exact approval
Scenario: app_isolation
 Given two apps with different selected goals
 When `app_isolation` checks the declared transition
 Then only that app choice and source facts are displayed
Scenario: no_effect
 Given any selectable goal
 When `no_effect` checks the declared transition
 Then no provider call or job or approval is created
```

## SHOULD - Technical
- Reuse guided tool routing, creative forms, campaign scope UI, results, telemetry and grants. No backend authority or credential changes in this slice.
- Local goal is presentation state, not evidence or execution input. Escape source text and use fixed actions.
- Remaining roadmap: outcome connection inventory, combined owner agreement, durable campaign schedules, packaged desktop and optional always-on worker.
- Preserve loopback desktop and independent native iOS product. Never publish the workstation server as hosted execution.

## Authorized parameters
GOAL_COUNT = 4
PRIMARY_NAVIGATION_COUNT = 3
