# Spec: agent-operation-contract
Status: draft

## MUST — Functional core
### Description
Expose an agent-neutral read-only capability contract before implementing broader autonomous execution. Capability discovery grants no access or approval.

### Requirements (EARS)
- The system shall return `operation_discovery` through an app-scoped GET with current app and policy hashes and supported resolution tool identifiers.
- The system shall return `checkpoint_boundaries` distinguishing existing provider maker/checker controls from unimplemented independent approval for general agent operations.
- The system shall reject `discovery_scope` requests for unknown apps, extra path segments or query overrides without changing stored state.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Discover capabilities
  Given a selected app
  When `operation_discovery` is requested
  Then supported tools and current hashes are returned
Scenario: Approval truth
  Given the current execution contract
  When `checkpoint_boundaries` are inspected
  Then missing independent approval and complete autonomous operation remain unimplemented
Scenario: Scope rejection
  Given an unknown app or query override
  When `discovery_scope` is requested
  Then stored state is unchanged
```

## SHOULD — Technical
- Existing loopback Host and Origin checks apply; no authentication bypass.
- No arbitrary code, provider actions, credentials or app-private record content in discovery.
- A compatible agent means a client that implements the documented protocol and authorized local access.

## WONT — Out of scope for this packet
- This discovery packet does not implement full autonomous operation or grants.
