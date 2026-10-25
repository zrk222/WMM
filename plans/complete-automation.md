# Plan: complete-automation
Spec: specs/complete-automation.md
Architect verdict: CONCERNS

## Architecture
Use an owner-confirmed versioned policy, separate from app preferences and agent
inference credentials. Activation depends on a current capability and credential
inventory for the selected workflows. Admission reuses existing scoped grants,
but standing owner approval replaces repeated checkpoints only inside its exact
action/target/content/resource envelope. Never treat an agent token as a human.

## Required architecture resolution before implementation
Implemented prerequisite packets now include `automation-readiness` and
`automation-standing-authority`: current-state credential inventory and bounded
local standing policy with gateway, commit and worker interlocks. The latter has
58 focused integration/regression tests and six rejected source mutations. It
does not implement the owner UI toggle, full automation PDF/data reports or the
blocked parent workflow adapters. This parent verdict covers that remaining
whole-feature scope; it is not a statement that local authority is absent.

The source-inspected design in `docs/complete-automation-authority.md` records
the workflow/credential/effect inventory, explicit owner summary and required
admission/revocation interlock. It identifies the existing consume-then-dispatch
gap and the read-only scope of social OAuth. This is design evidence only; the
executable inventory, transactional implementation and acceptance proof below
are still required. The verdict stays CONCERNS until those architecture contracts
are executable and the implementation plan is sealed.

The current operation catalog covers a bounded local subset. Define the workflow
to operation/credential/effect map for every selectable complete-automation path.
Identify the authoritative fresh verification and expiry facts for each existing
connection family. Specify transactional policy revocation/resource reservation
and how queued/remote work is stopped or reconciled. Preserve existing provider
action checker semantics unless a separately authorized policy explicitly covers
the exact proposed effect. These decisions need executable positive/negative
contracts, not a cosmetic switch or an unchecked generic administrator flag.

## Tasks
- [ ] T0 | slice=docs | files=docs/complete-automation-authority.md | verify=`specline strict complete-automation` | Define the owner journey, exhaustive operation and credential mapping, transaction boundary, revocation semantics and executable acceptance needed before activation.
- [ ] T1 | slice=mission_control | files=mission_control/complete_automation.py,mission_control/automation_requirements.py,mission_control/db.py | verify=`python -m unittest tests.test_complete_automation -v` | Resolve owner_activation, credential_readiness, scope_summary, grant_binding, authority_separation and authority_restore.
- [ ] T2 | slice=mission_control | files=mission_control/agent_grants.py,mission_control/operation_runtime.py,mission_control/complete_automation.py | verify=`python -m unittest tests.test_complete_automation -v` | Implement scoped_execution, continuous_validation and revocation with atomic admission and durable uncertainty reconciliation.
- [ ] T3 | slice=mission_control | files=mission_control/server.py,mission_control/static/complete-automation.js,mission_control/static/app.js,mission_control/static/index.html | verify=`python -m unittest tests.test_complete_automation_http -v` | Deliver the real owner UI switch, credential onboarding links, explicit scope confirmation and shared service routes.
- [ ] T4 | slice=tests | files=tests/test_complete_automation.py,tests/test_complete_automation_http.py,tests/test_complete_automation_clients.py | verify=`python -m unittest tests.test_complete_automation tests.test_complete_automation_http tests.test_complete_automation_clients -v` | Prove all ten acceptance scenarios, races, two independent clients and human approval separation.
- [ ] T5 | slice=mission_control | files=mission_control/complete_automation_reports.py,mission_control/static/complete-automation.js | verify=`python -m unittest tests.test_complete_automation_reports -v` | Deliver automation_reports with exact KPI history and secret-redacted PDF/data exports.

## Gates
CF doctor, strict requirement mutation, resolved architecture and pre-code seals;
source mutation and full regression; actual authenticated owner/agent/browser
workflow evidence; Prestige deterministic audits and mobile/accessibility checks;
hash-bound workflow audit. Current CONCERNS is not an implementation or release
pass. External accounts, paid effects and publication remain separately scoped.
