# Spec: campaign-monitor
Status: draft

## MUST - Functional core
### Description
Provide owner-reviewed finite monitoring of exact existing campaign intents. The monitor reconciles existing receipts and can pause only an identified paid campaign after an explicitly approved fresh observation condition. It never publishes, creates or activates advertisements.

### Requirements (EARS)
- The system shall reject foreign owners, changed scope or target hashes and unsupported protective conditions through `approval_boundary`.
- The system shall store an immutable owner proposal with cadence from 30 to 3600 seconds, expiry less than or equal to campaign expiry, one through 100 runs and one through 160 provider boundary units through `finite_plan`.
- The system shall enqueue at most 20 due monitor jobs per tick without duplicate pending work through `durable_tick`.
- The system shall reject changed host, job input, lease, owner, credentials or scope at every provider boundary through `retained_capability`.
- The system shall return verified protective pause only after fresh approved drift or active-after-end evidence while retaining media commitments through `protective_pause`.
- The system shall block automatic replay after interrupted work or uncertain pause and return reconciliation guidance through `uncertainty`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: approval_boundary
  Given exact existing intents and changed or foreign resources
  When `approval_boundary` prepares or activates a monitor
  Then only the current owner and matching immutable source hashes are accepted
Scenario: finite_plan
  Given finite valid and invalid owner choices
  When `finite_plan` validates monitoring
  Then cadence, expiry and resource bounds are enforced without new campaign authority
Scenario: durable_tick
  Given due active monitors and concurrent scheduler calls
  When `durable_tick` admits jobs
  Then at most 20 unique jobs are enqueued per tick and pending work is not duplicated
Scenario: retained_capability
  Given a leased monitor job and a changed authority revision
  When `retained_capability` reaches a provider boundary
  Then current host job and selected resource checks deny the changed capability
Scenario: protective_pause
  Given a current identity-matched drift observation and an approved protective condition
  When `protective_pause` runs
  Then the saved owned campaign is confirmed paused and its commitment remains held
Scenario: uncertainty
  Given an interrupted provider status mutation
  When `uncertainty` restarts monitoring
  Then no mutation is automatically replayed and saved uncertainty requires review
```

## SHOULD - Technical
- Only exact existing intent IDs with request hashes are selected; no wildcard future intents or batch expansion.
- Provider boundary admission reserves monitor units independently of existing campaign emergency allowances.
- Owner approval is exact proposal hash activation; OFF invalidates new admissions and cancels queued monitor jobs.
- Current owner, app, connection/config and host datastore checks remain mandatory. No owner actor impersonation bypass.
- No spend threshold conversion, causal measurement or live provider acceptance claim.

## Current integration and target limits
- Root must wire the owner router, policy checker, worker special dispatch and supervision hook, and prevent automatic monitor-job reclaim/retry. A returned execute status BLOCKED must persist as job BLOCKED rather than generic worker success.
- active_after_end operates only when an approved ad end precedes both monitor and campaign scope expiry; all monitoring stops at expiry. This is not indefinite protective authority.
- First version selects existing intent IDs only. No future batch expansion, provider live acceptance, spend conversion or growth guarantee is established.
