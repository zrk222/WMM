# Spec: automation-owner-ui
Status: draft

## MUST - Functional core
### Description
Deliver real owner controls over implemented standing authority with explicit
credential onboarding and scope confirmation. Retain all incomplete workflow
families as visible blockers, and keep live telemetry alongside the controls.

### Requirements (EARS)
- The system shall display saved OFF, ACTIVE or BLOCKED authority from the owner service and never infer activation from a preference through `owner_status`.
- The system shall present selected workflows, agent identity, connection verification and limits of 1 through 24 hours, 1 through 10000 calls and 1 through 8 concurrent work units before scope review through `onboarding_scope`.
- The system shall display the exact server summary and its blockers and require explicit owner confirmation before enabling its hash-bound scope through `confirm_scope`.
- The system shall switch the exact current policy OFF through the owner service and display the saved revocation result through `owner_off`.
- The system shall clear once-only token delivery on dialog close or app/identity change and reject stale or duplicate submissions through `scope_lifecycle`.
- The system shall return secret-free execution counts, printable PDF metadata and downloadable data for saved automation authority through `automation_reports`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: owner_status
  Given no standing scope or an expired saved policy
  When `owner_status` loads
  Then OFF or BLOCKED is visible without false activation
Scenario: onboarding_scope
  Given selected accounts and connection profiles
  When `onboarding_scope` is reviewed
  Then verification dates, missing prerequisites and exact resource limits are visible
Scenario: confirm_scope
  Given an incomplete workflow or a current ready summary
  When `confirm_scope` is requested
  Then blocked scope cannot activate and ready scope requires explicit confirmation
Scenario: owner_off
  Given an active policy revision
  When `owner_off` is confirmed
  Then the service revokes that revision and the UI reflects OFF
Scenario: scope_lifecycle
  Given a pending response followed by app change
  When `scope_lifecycle` receives the response
  Then the old scope and its token are not shown in the new app
Scenario: automation_reports
  Given saved policies and executions
  When `automation_reports` are exported
  Then policy/action counts and outcome hashes appear without credentials or private operation input
```

## SHOULD - Technical
- Use the current independently authenticated owner POST routes. The setup catalog
  includes every workflow and blocker; no endpoint creates authority on read.
- Keep the initial action a switch-style control opening scope review. Enabling
  occurs only on final server confirmation, not on the initial click. OFF is
  enabled for saved active authority even when its effective state is BLOCKED.
- Reuse page-reporting PDF preview and protected once-only token patterns. The
  export includes public scope and hashes, not tokens, raw operation input/result
  or profile secret references. Unknown spend remains unknown; ceiling is zero.
- App/release/identity revisions bind asynchronous UI responses. Preserve inputs
  after failure. Clear secrets on close and no token in markup, reports or state.
- Existing Nanna page/form guidance must cover the added form. The live monitor
  remains available on the same page. Broader adapters remain parent requirements.

## Authorized parameters
MAX_HOURS = 24
MAX_CALLS = 10000
MAX_INFLIGHT = 8
Synthetic acceptance choices below include values required to be rejected;
they do not raise production ceilings.
max_calls = 2
max_calls = 10001
max_inflight = 9
