# Spec: agent-reviewed-dispatch
Status: draft

## MUST - Functional core
### Description
Connect scoped agent grants to the existing durable human checkpoint lifecycle for exact local operations. This backend packet adds opt-in immutable per-grant review policy and reviewed request preparation/inspection/execution services. Human HTTP/UI and CLI/MCP entry points remain required integration work. Existing owner-issued grants without review policy retain their current bounded local behavior. No provider effect enters this scope.

### Requirements (EARS)
- The system shall store an immutable owner-selected subset of granted local write operations requiring independent human review through `review_policy`.
- The system shall reject ordinary dispatch for any operation requiring review before the service executes through `enforced_checkpoint`.
- The system shall store an immutable exact envelope and grant-bound input hash with a durable waiting checkpoint under the delegated owner as maker through `frozen_request`.
- The system shall reject self approval, stale checker or maker role versions, changed app state, revoked grants, expired grants with maximum lifetime 24 hours and edited input before exclusive claim through `reviewed_admission`.
- The system shall execute the saved authoritative operation once after approved admission and store its result or explicit unknown outcome for durable inspection through `reviewed_execution`.
- The system shall store cancelled or uncertain checkpoint state without automatic replay, and exclude review authority from snapshots through `reviewed_recovery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: review_policy
  Given an owner-issued local grant
  When `review_policy` is exercised
  Then only an immutable subset of its granted write operations requires review
Scenario: enforced_checkpoint
  Given a grant requiring review for a local write
  When `enforced_checkpoint` is exercised
  Then the ordinary gateway rejects that write without changing domain history
Scenario: frozen_request
  Given an authenticated delegated agent
  When `frozen_request` is exercised
  Then saved input and grant binding are immutable across replay and restart
Scenario: reviewed_admission
  Given a pending exact request and independent checker
  When `reviewed_admission` is exercised
  Then only a current approved request can be claimed once
Scenario: reviewed_execution
  Given a claimed saved request
  When `reviewed_execution` is exercised
  Then authoritative history and stored result match and repeated execution is rejected
Scenario: reviewed_recovery
  Given cancelled work or an uncertain result
  When `reviewed_recovery` is exercised
  Then inspection retains the durable receipt without rearming execution
```

## SHOULD - Technical
- Review policy is optional at issuance and immutable thereafter; changing it requires a new grant. Review operations must be a subset of granted POST operations. No human approval or policy change operation is present in the agent catalog.
- Request identity is app-scoped; saved input hash binds the entire envelope and grant ID. Owner role/version is inherited from the authentic delegation. It does not impersonate a newly authenticated human action; the separate checker must authenticate independently through the human adapter.
- Preparation and execution each consume one granted attempt. Grant and checkpoint currentness are rechecked before claim. Already admitted work may finish after later revocation. Cancellation during execution retains a reconciliation-required state with a durable result receipt. No automatic retries.
- Generic service exceptions are recorded as UNKNOWN without raw exception text. Domain validation errors are FAILED with a fixed safe code. A crashed RUNNING operation remains reconciliation-required; it is never automatically repeated.
- The existing 24 hours checkpoint expiry, 10000 calls grant ceiling, body cap 16777216 bytes and HTTP timeout 15 seconds remain. All tests use synthetic identity and isolated databases. Full runtime sandboxing, remote approval, full-domain coverage, provider effects and genuine human/provider acceptance remain required separately.

## Authorized parameters
max_calls = 10
max_calls = 100
max_workers = 4
