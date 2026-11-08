# Server-side authority enforcement audit

**Date:** 2026-11-08
**Scope:** Are agent grants, spend budgets, roles and AGENT origin enforced by the
server before effects, or merely recorded?
**Method:** Source review of the admission, protected-operation, budget and
provenance paths plus targeted negative tests. No live provider account was used.

## Verdict

**Enforced server-side.** This pass found no request body that can widen a grant,
budget, role or origin. Every path reviewed re-derives authority from stored
state and re-checks it at the protected operation boundary.

## Grants

| Control | Enforcement |
| --- | --- |
| Token identity | Bearer token hashed at rest; unknown token denied (`agent_grants.authenticated`). |
| App and operation scope | Admission rejects an envelope whose app or operation is not in the stored grant. |
| Owner membership | Admission requires the recorded owner to still hold `OWNER` at the recorded role version. |
| App drift | Admission rejects if the app version or manifest hash differs from the grant. |
| Expiry | Effective expiry is recomputed from stored consent records; expired grants are denied. |
| Quota | `used >= max_calls` denied; admission increments once inside the same transaction. |
| Revocation | `status != ACTIVE` denied on every admission. |
| Review policy | Owner-selected write operations require an exact prepared review; ordinary dispatch is refused. |
| Standing execution | A live standing execution must match store, grant, operation, envelope hash and `DISPATCHED` status. |
| Re-check | `protected()` re-runs the same check at operation entry and again before commit. |

Key code: `mission_control/agent_grants.py` (`current`, `authenticated`, `admit`),
`mission_control/operation_authority.py` (`check_agent`, `check_standing`,
`protected`), `mission_control/automation_execution.py` (`execute_admitted`).

## Budgets

| Control | Enforcement |
| --- | --- |
| Automation spend | `spend_limit_minor` must equal the fixed zero limit; any other value fails before issuance. |
| Campaign per-campaign budget | `check_ad_limits` rejects a budget above the approved `max_campaign_minor` and an end time past scope expiry. |
| Campaign aggregate | Reservation rejects when campaign count exceeds `max_campaigns` or retained account commitment plus the new budget exceeds `max_total_minor`. |
| Campaign content/rights/targeting | Approved hashes must contain the exact submitted hashes. |
| Publication calls | DB triggers make approval, expiry, `max_calls` and `calls_used` immutable except through the approved transition; charge only increments while `APPROVED` and below the cap. |
| Expiry | Every budget/approval clock is recomputed from stored consent receipts, not the request. |

Key code: `mission_control/complete_automation.py` (`proposal_data`),
`mission_control/campaign_execution.py` (`check_ad_limits`, `_reserve_ad`),
`mission_control/publication_authority.py` (triggers, `charge`).

## AGENT origin and roles

| Control | Enforcement |
| --- | --- |
| AGENT origin | Derived only from the server-side request context (`grant_id` present). Request bodies with `origin`, `provenance` or `setup_sources` are rejected by exact-key validation. |
| Owner-only routes | Owner actions require a freshly verified session principal and current `OWNER` role version. |
| Role escalation | Member setup accepts only `MAKER` or `CHECKER`; `OWNER` cannot be assigned or replaced through member setup. |
| Extra identity fields | Member and grant requests use exact key sets, so `principal`, `owner`, `used`, `status`, `app_hash`, `token_hash` cannot be supplied. |

Key code: `mission_control/setup_approval.py` (`provenance`), `mission_control/review_access.py`
(`member_body`, `save`), `mission_control/agent_grants.py` (`issue_data`).

## Negative tests added

`tests/test_authority_enforcement.py` proves:

- setup apply rejects body-injected `origin`, provenance and `setup_sources`; only the server grant context produces `AGENT`;
- grant issuance rejects `used`, `status`, `app_hash`, `owner`, `grant_id` and `token_hash`;
- automation scope rejects non-zero spend, boolean spend and extra fields;
- campaign scope rejects over-cap budgets, invalid counts, empty approved hashes and extra fields;
- member setup rejects `OWNER` and extra identity fields;
- publication activation rejects spoofed `calls_used`/`owner` and the DB refuses to raise `max_calls` after approval.

Existing suites already cover cross-app/operation denial, quota races,
revocation, expiry, changed app/owner versions, publication charge caps and
stale approvals (`tests/test_agent_grants.py`, `tests/test_publication_authority.py`,
`tests/test_campaign_execution.py`, `tests/test_setup_approval.py`).

## Residual risks (not code bypasses)

1. **Process:** every PR is currently solo-merged. A second human reviewer on
   security-sensitive changes is still required and cannot be supplied by code.
2. **Local owner session:** the loopback server trusts the workstation. Host
   compromise or a same-user process remains outside this model.
3. **Bearer tokens:** grants are hashed at rest and delivered once, but a leaked
   live token is usable until expiry/revocation within its scoped operations.
4. **Provider truth:** accepted authority is not provider delivery. Publication,
   campaign and analytics outcomes still require provider readback and live
   evidence.
5. **macOS:** the desktop credential adapter remains unsupported; this audit did
   not exercise macOS key storage.
6. **Measured growth:** no install, retention or conversion result is established
   by this audit.
