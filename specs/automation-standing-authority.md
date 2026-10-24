# Spec: automation-standing-authority
Status: draft

## MUST - Functional core
### Description
Implement owner-confirmed standing approval and its enforcement for selected
implemented workflows. Preserve explicit blockers for incomplete parent workflows.
No saved preference, inventory read, model instruction or agent bearer can issue
standing approval. The owner UI and final cross-workflow acceptance remain required.

### Requirements (EARS)
- The system shall present a hash-bound owner scope containing the agent, app, workflow actions, selected credentials, purpose, expiry within 24 hours, 1 through 10000 calls, 1 through 8 concurrent work units and zero spend through `scope_confirmation`.
- The system shall store a versioned standing policy and its bound agent grant in one owner transaction only after the exact current summary and required onboarded access pass verification through `atomic_activation`.
- The system shall reserve one call and enforce the exact operation, policy, app, credential revisions and concurrent-work allowance before dispatch through `bounded_admission`.
- The system shall reject a local business commit when its standing policy, owner role, app or selected credential facts ceased to be valid before that commit through `commit_interlock`.
- The system shall attach standing authority to its queued local preparation jobs and recheck it at owned worker dispatch and commit through `worker_scope`.
- The system shall return a receipt that revokes future admissions and cancels undispatched owned work when the owner disables the exact current policy revision through `scope_revocation`.
- The system shall retain action hashes, committed-write counts and known or uncertain outcomes without exporting tokens or restoring standing authority from snapshots through `execution_receipts`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: scope_confirmation
  Given selected workflows and exact current verified credentials
  When `scope_confirmation` prepares the owner summary
  Then every permitted action and resource boundary is explicit without authority issuance
Scenario: atomic_activation
  Given a stale summary or an agent principal
  When `atomic_activation` is attempted
  Then no standing policy or grant is created
Scenario: bounded_admission
  Given a policy with one call and one concurrent work unit
  When `bounded_admission` races multiple requests
  Then only its permitted allowance is reserved
Scenario: commit_interlock
  Given admitted work followed by policy revocation
  When `commit_interlock` attempts a business write
  Then that write cannot commit
Scenario: worker_scope
  Given a queued policy-owned job and an unrelated job
  When `worker_scope` is revoked before worker dispatch
  Then the owned job cannot execute and unrelated work is preserved
Scenario: scope_revocation
  Given a current owner and an obsolete policy revision
  When `scope_revocation` disables each scope
  Then only the exact current revision revokes its grants and work
Scenario: execution_receipts
  Given work with a committed local effect followed by a lost result
  When `execution_receipts` are inspected
  Then the outcome remains uncertain and no automatic resubmission occurs
```

## SHOULD - Technical
- Reuse the current owner membership, operation catalog, typed domain services and
  credential inventory. Share one SQLite read/write snapshot for policy checks.
  Activation checks protected access and current official tool identity without
  paid inference. Unknown or incomplete workflow adapters block selection.
- The current executable subset is local evidence, local experiment preparation
  and local pipeline preparation. All 11 parent workflow families remain visible;
  adding media, discovery, editing, analytics, release and paid-effect adapters is
  still mandatory under the parent goal. This packet cannot claim full WMM scope.
- Store opaque policy/grant links separately from app JSON and exports. Preview
  requires the current independently authenticated owner and never returns a key.
  Activation returns a random bearer token once; persist its hash only.
- Use a ContextVar carrying only the exact store/policy/execution binding for
  fixed dispatch. The central SQLite context checks policy before commit and
  counts successful business write transactions in that same transaction. It
  cannot grant new operations. Ordinary unlinked grants retain existing behavior.
- A queued job inherits the admitted execution binding in its enqueue transaction.
  The worker checks authority before starting and during database commits. Result
  recording occurs outside execution authority so OFF cannot erase the receipt.
  Only currently mapped local preparation can execute; unsupported provider effects
  remain blocked. Future external adapters require saved remote IDs and explicit
  cancellation/reconciliation contracts before entering this map.
- Admission and OFF use BEGIN IMMEDIATE. Work already dispatched can have committed
  effects; OFF does not claim to undo them. Known validation failure without a
  committed business transaction is failed; a failure after commits is unknown.
  Cancellation and revocation never silently refund calls or resubmit work.
- Read operations and explicit local cancellation remain usable at a concurrency
  ceiling, subject to call allowance; owner status/OFF do not consume agent calls.
  Credential freshness and availability are distinct: inspect saved revisions at
  every boundary and check required protected access at activation/admission.
- Owner service routes use existing fresh identity/CSRF controls. The bearer
  gateway executes with the admitted binding. No CLI/MCP management tool permits
  an agent to activate, expand or approve its own policy.

## Authorized parameters
MAX_CALLS = 10000
MAX_INFLIGHT = 8
MAX_HOURS = 24
SPEND_LIMIT_MINOR = 0
MAX_WORKFLOWS = 11
MAX_ACCOUNTS = 20
FRESH_HOURS = 24
timeout = 15

Acceptance test inputs:
These are synthetic test choices, including explicitly invalid values whose
rejection is required. They do not expand the production ceilings above.
max_calls = 1
max_calls = 20
max_calls = 10001
max_inflight = 0
max_inflight = 1
max_inflight = 9
max_workers = 1
max_workers = 8
