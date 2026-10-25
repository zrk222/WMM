# Spec: complete-automation
Status: draft

## MUST - Functional core
### Description
Offer complete automation for user-selected WMM workflows under one
explicit owner-approved scope. Verify required credentials before activation,
show the scope and its effects in plain language, and enforce the same authority
for agents and the human UI. This is execution permission, distinct from automatic
planning defaults. No existing or added goal feature is omitted by this work.

### Requirements (EARS)
- The system shall return OFF for complete automation until the independently authenticated owner confirms the current explicit scope summary through `owner_activation`.
- The system shall reject activation when any credential or executable capability required by a selected workflow is missing, unverified within 24 hours, expired or bound to a different app or account through `credential_readiness`.
- The system shall return an explicit summary of agent identity, app and release, workflows and actions, accounts and destinations, content and rights constraints, expiration within 24 hours, 1 through 10000 calls, at most 180 seconds per owned command, currency and a zero-default spend ceiling, stop rules and revocation through `scope_summary`.
- The system shall store a versioned standing grant bound to the exact app, policy, credential and account revisions and reject a stale summary at activation through `grant_binding`.
- The system shall permit in-scope actions without repeated human checkpoints and reject actions outside the standing grant or resource bounds through `scoped_execution`.
- The system shall reject agent attempts to enable, extend or approve their own complete-automation scope through `authority_separation`.
- The system shall stop affected execution when credentials, policy, rights, targets or budgets cease to satisfy the standing grant and return the explicit repair requirement through `continuous_validation`.
- The system shall revoke future admissions when the user switches OFF and store cancellation or reconciliation state for already-dispatched owned work through `revocation`.
- The system shall emit secret-redacted action, approval, usage and outcome history plus PDF and data reports through `automation_reports`.
- The system shall reject imported snapshots, handoffs or restored preferences as a source of active automation authority through `authority_restore`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: owner_activation
  Given no confirmed current owner scope
  When `owner_activation` is inspected
  Then the switch is OFF and no execution grant is issued
Scenario: credential_readiness
  Given a selected workflow with a missing or stale credential
  When `credential_readiness` is checked
  Then activation is rejected and the missing account capability is shown
Scenario: scope_summary
  Given selected workflows and configured accounts
  When `scope_summary` is presented
  Then the user can read every permitted action, target, limit and stop condition without secrets
Scenario: grant_binding
  Given a summary followed by a changed account or policy revision
  When `grant_binding` is activated
  Then the stale confirmation is rejected
Scenario: scoped_execution
  Given a valid bounded standing grant
  When `scoped_execution` attempts an allowed action and an outside-scope action
  Then the allowed action proceeds and the outside-scope action requires a human checkpoint
Scenario: authority_separation
  Given an agent bearer credential
  When `authority_separation` attempts a policy expansion
  Then no owner approval or replacement grant is created
Scenario: continuous_validation
  Given an active grant and a revoked account or exhausted budget
  When `continuous_validation` checks the next admission
  Then affected work stops with its exact repair action
Scenario: revocation
  Given active complete automation
  When `revocation` switches the scope OFF
  Then future admissions stop and dispatched work has explicit cancellation or reconciliation status
Scenario: automation_reports
  Given saved in-scope executions
  When `automation_reports` are exported
  Then action and outcome records retain provenance and missing values without credential contents
Scenario: authority_restore
  Given a snapshot containing a prior active preference
  When `authority_restore` imports the snapshot
  Then no standing execution authority is restored
```

## SHOULD - Technical
- Reuse independent owner authentication, scoped agent grants, durable jobs,
  operation validators, protected credentials and audit history. The existing
  growth_mode preference is not an execution grant.
- Build a scope-specific onboarding inventory from implemented workflow
  requirements. Saving a connection is CONFIGURED_UNTESTED until a real test.
  Preserve account subject, permitted scopes, connection revision, last successful
  verification, expiry and renewal state without exposing keys or refresh tokens.
- Activation is an optimistic, transactional owner confirmation of the exact
  summary hash. No checkbox may directly update app JSON and bypass admission.
  Missing implementation is a capability blocker, not evidence of full operation.
- Keep zero spend by default. Unknown price, billing or subscription allowance
  remains UNKNOWN; require explicit configured limits before paid effects. No
  fallback changes account/provider/destination without new owner authorization.
- Delegated actions inside a standing scope need no repeated per-action approval.
  Binding changes, boundary expansions, new destinations and exhausted resources
  require owner review. Approval and dispatch use the same policy revision.
- Revocation must interlock with admissions and resource reservations. External
  effects already dispatched are reconciled by saved remote ID, never blindly
  retried or called cancelled from a local preference change.
- Human UI, CLI and MCP use the same service and receipts. Provide keyboard and
  screen-reader switch operation, visible OFF/ON/BLOCKED states, inline errors,
  loading/empty states, onboarding links and accessible desktop/mobile summaries.
- All source discovery, video creation/editing, experiment, analytics and release
  workflows selected by the owner remain in final acceptance. Do not advertise
  complete automation after proving only planning or a local backend subset.
