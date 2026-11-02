# Spec: campaign-execution
Status: draft

## MUST - Functional core
### Description
Implement a narrowly scoped Facebook Page publishing and Meta advertising adapter. Owner approval binds exact app, Page, account, content and finite liability; agents cannot create approval.

### Requirements (EARS)
- The system shall bind owner scope to current app and policy revisions, selected Page and optional ad account, finite expiry, permissions and approved content and rights hashes through `scope_binding`.
- The system shall reject each effect when current owner membership, app manifest, provider entitlement, target or scope validation fails through `effect_admission`.
- The system shall persist one unique request intent and its maximum liability atomically before provider mutation through `durable_admission`.
- If a mutation result is unknown, the system shall store its commitment and reject blind replay through `unknown_recovery`.
- When a Page post is published, the system shall save its exact returned ID and read it back through `post_readback`.
- When an ad is activated, the system shall save each object ID, verify one finite lifetime budget and end time, and retain commitment through `paid_budget`.
- When scope is revoked or expires after at most 24 hours, the system shall reject new effects and permit protective pause and readback through `protective_stop`.
- The system shall reject credentials from persistent intent and public results through `secret_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: scope_binding
  Given an exact owner summary and current app revision
  When `scope_binding` activates that summary
  Then a changed summary or app revision cannot be activated
Scenario: effect_admission
  Given missing Page permission or a changed membership
  When `effect_admission` checks a provider effect
  Then no mutation is transmitted
Scenario: durable_admission
  Given one remaining campaign budget and concurrent requests
  When `durable_admission` reserves both
  Then only one request can reserve the remaining amount
Scenario: unknown_recovery
  Given a provider request whose response is lost
  When `unknown_recovery` observes the intent after restart
  Then the held amount remains and no automatic resubmission occurs
Scenario: post_readback
  Given a successful fixed Page feed request
  When `post_readback` reads its returned post ID
  Then the saved result distinguishes verification from creation
Scenario: paid_budget
  Given an approved finite lifetime media budget and end time
  When `paid_budget` activates the saved ad objects
  Then their IDs and verified provider budget remain durable
Scenario: protective_stop
  Given a revoked scope with a saved remote campaign
  When `protective_stop` pauses that campaign
  Then no new activation is admitted and the pause result is read back
Scenario: secret_boundary
  Given protected credentials and provider errors
  When `secret_boundary` stores and returns receipts
  Then neither credentials nor raw response bodies appear in receipts
```

## SHOULD - Technical
- Reuse protected Facebook credentials and pinned fixed-host transport. Reject arbitrary paths and parameters.
- Bind content and targeting to canonical hashes. Rights hashes record owner attestations, not proof of rights.
- Preserve remote IDs and budget holds after restart, revocation, timeout and partial creation. No local polling claim replaces provider budget enforcement.
- Provider fees, taxes, foreign exchange, reporting delays and account-specific billing are outside the approved media budget; show uncertainty before approval.
- Each scope has separate PAUSE, RECONCILE and RECOVERY allowances of 160 provider-boundary checks; these permit no new spend and do not replace current access checks.
- A pending paid operation uses an OS-backed per-intent owner lock and a durable owner-token lease. Only a free lock and an exact matching lease, status and identity snapshot permit read-only reconciliation to UNKNOWN; legacy unowned pending records remain blocked for inspection.
- A currently authenticated owner may inspect and stop the exact saved account and campaign after app or owner-role revision changes; scoped agents remain bound to their original app and grant checks. The unchanged saved credential, destination and exact provider object account remain required.
- Protective pause and read-only recovery do not require current billing funding, active-account status or matching currency; those conditions remain mandatory for new paid execution.
- A safety pause is a point-in-time provider readback. Interrupted or delayed remote work can remain uncertain, and commitment holds are not released by the local recovery path.
- Live publication and paid acceptance remain NOT_RUN without separate user authorization.

## Authorized parameters
MAX_HOURS = 24
MAX_POSTS = 100
MAX_CALLS = 500
MAX_CAMPAIGNS = 20
MAX_BODY_BYTES = 32768
timeout = 30
SAFETY_CALL_LIMIT = 160
limit = 50
timeout = 15

Acceptance test inputs (synthetic choices, not production ceilings):
max_posts = 2
max_calls = 50
max_campaigns = 0
max_campaign_minor = 0
max_total_minor = 0
max_workers = 2
timeout = 10
