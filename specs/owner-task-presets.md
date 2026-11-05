# Spec: owner-task-presets
Status: owner-authorized implementation design

## MUST - Functional core
### Description
Reduce manual catalog selection in the existing owner grant form. The owner chooses Research only, Organic marketing or Bounded Meta media buyer; WMM prepares an explicit editable operation proposal and explains its effects. This is one increment toward the full goal agreement, execution, exception and report loop, not completion of that loop.

### Requirements (EARS)
- When the owner opens grant setup, the system shall return exactly 3 named task choices and a Custom choice through `task_choices`, without choosing an agent, account or effect authority for the owner.
- When Research only is selected, the system shall return a fixed declared operation set checked against an explicit read-effect allowlist through `research_profile`, with 0 publish, spend, render or local-write operations.
- When Organic marketing is selected, the system shall return the fixed supported research, source/brief, Hypit/editor, publication and reporting operation set through `organic_profile`, with 0 automatically accepted source reuse, artifact or destination approvals.
- When Bounded Meta media buyer is selected, the system shall return its fixed supported operation set and explicit paid-account/budget approval explanation through `meta_profile`, with 0 newly issued provider authority.
- If an operation is absent or its effect differs from the declared contract, the system shall reject the preset through `profile_unavailable` with 0 silently dropped operations and retain Custom editing.
- When a preset is selected, the system shall return the operation checkbox selection and existing independent-review defaults through `editable_scope`, preserve owner-entered agent/date fields, and mark advanced operation changes as Custom.
- When the grant form renders, the system shall return the selected deadline and default 20 total lifetime calls through `allowance_explanation`, with the full catalog under optional advanced disclosure and 0 claimed automatic weekly resets.
- When the owner switches profiles or edits advanced operations, the system shall return the effect summary through `scope_summary` before issuing, with 0 automatic issue requests.
- If the app, owner, catalog or selected form changes, the system shall reject stale submission through `context_binding` using existing server and UI checks.
- When desktop and mobile owners use setup, the system shall return accessible labels, keyboard-operable choices and visible unavailable/custom states through `accessible_setup` at 1440 px and 390 px without horizontal overflow.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: task_choices
 Given the existing owner grant form
 When `task_choices` is rendered
 Then the owner sees three named tasks and Custom
Scenario: research_profile
 Given the fixed research contract
 When `research_profile` resolves against the real catalog
 Then every selected effect is an allowed read and no write is selected
Scenario: organic_profile
 Given the fixed organic contract
 When `organic_profile` prepares a proposal
 Then its required supported operations and remaining external approval needs are visible
Scenario: meta_profile
 Given the fixed media buyer contract
 When `meta_profile` prepares a proposal
 Then supported paid effects require exact separate campaign authority
Scenario: profile_unavailable
 Given an absent or changed required catalog effect
 When `profile_unavailable` resolves the task
 Then the preset is unavailable and no reduced substitute is issued
Scenario: editable_scope
 Given owner-entered agent and dates
 When `editable_scope` changes a task or advanced selection
 Then operation defaults update and owner inputs are preserved
Scenario: allowance_explanation
 Given the default total call limit
 When `allowance_explanation` renders
 Then the total until expiry is explicit and no weekly refill is claimed
Scenario: scope_summary
 Given a selected task
 When `scope_summary` is inspected
 Then its effects are explicit and selecting it sends no issue request
Scenario: context_binding
 Given a stale app or owner form
 When `context_binding` submits
 Then the existing current-scope check rejects it
Scenario: accessible_setup
 Given desktop and mobile viewports
 When `accessible_setup` is operated by keyboard
 Then task choice and advanced controls remain readable and usable
```

## Architecture and limits
Reuse agent-control.js, the served catalog and existing Grants.issue. No new credential system, background executor, operation name, autonomous approval or provider adapter. Explicit fixed effect contracts are checked against the current catalog; HTTP method is not an effect classifier. This change does not complete combined agreement activation, shared budgets, cross-scope Stop or the complete Hypit organic cycle. Those remain in the existing goal and must not be described as implemented here.

## Authorized parameters
max_calls = 20
DEFAULT_CALLS = 20
DEFAULT_HOURS = 1
timeout = 5
