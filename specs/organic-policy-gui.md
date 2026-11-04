# Spec: organic-policy-gui

## MUST - Functional core
### Description
Let a current app owner create, inspect and revoke the existing organic video
production policy from Research. Use existing policy enforcement, local Hypit
generation and exact owner HTTP routes. This screen does not publish a video.

### Requirements (EARS)
- The system shall return a typed owner policy form through `policy_form`, selecting tested Page connection, current source rights, proven claims, literal captions, exact output hashes or explicit standing-generated mode, expiry at most 24 hours away and finite existing quotas.
- The system shall return a full normalized app-bound proposal before explicit owner confirmation through `policy_review`, retaining exact source, claim, template, destination, schedule expiry, model currency and zero provider service budget.
- The system shall reject stale app, principal, role-version or session context through `policy_context`, binding the GUI create request to exactly its reviewed app version, app hash, owner role version, session binding and Page binding inside the policy transaction.
- The system shall retain exact uncertain create and revoke requests through `policy_recovery`, bind history lookup to the request hash, inspect saved state before an explicit identical request and never infer rejection from a failed readback.
- The system shall return saved policy history of at most 100 items per page and current revalidation status through `policy_history`, showing held generation and admission capacity distinctly from delivered posts and retaining expired and revoked receipts.
- The system shall return complete policy JSON and PDF reports through `policy_reports`, keeping model cost, authority, admitted outputs and external delivery distinct.
- The system shall return labeled, keyboard-usable controls through `policy_accessibility`, with a 390 pixel mobile viewport, visible validation and useful empty/failed states.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: policy_form
  Given a current app owner with eligible sources and a tested Page connection
  When the owner selects exact evidence and finite production settings
  Then the existing policy validator receives the typed proposal
Scenario: policy_review
  Given a typed proposal
  When the owner reviews its exact normalized fields
  Then only explicit confirmation saves that exact policy
Scenario: policy_context
  Given an open policy form
  When the app or owner session changes
  Then the prior form cannot save under the new context
Scenario: policy_recovery
  Given an acknowledged save followed by failed readback
  When the owner inspects or explicitly repeats the identical request
  Then the same durable identity is retained without another policy
Scenario: policy_history
  Given saved current, expired and revoked policies
  When owner history is opened
  Then each saved state and held capacity is visible without claiming publication
Scenario: policy_reports
  Given an exact saved policy
  When reports are exported
  Then source hashes, limits, usage and evidence boundaries are preserved
Scenario: policy_accessibility
  Given desktop and narrow mobile owner sessions
  When the controls are used with keyboard and invalid inputs
  Then labels, error guidance and focus remain usable without horizontal overflow
```

## Authorized parameters
POLICY_UI_REQUEST_TIMEOUT_MS = 30000
POLICY_UI_PENDING_LIMIT = 25
POLICY_UI_MAX_TEMPLATES = 20
max_generations = 1
max_posts = 1
max_calls = 20
max_model_minor = 0

## Non-goals
No new renderer, provider, model charge, social destination, campaign scope or
agent owner authority. No automatic execution, source rights declaration or post.
