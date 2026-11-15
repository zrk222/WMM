# Plan: durable-rule-proposals
Spec: specs/durable-rule-proposals.md
Architect verdict: PASS

Reuse Automation Rules in Results, the owner session check, the saved-rule verifier, the existing database snapshot projector and the supervised worker. The proposal inbox and optional finite schedule keep private app evidence separate. One write transaction checks authority, evaluates bounded local facts, retains proposals and advances a due slot. Save exact run and proposal hashes; preserve reviewer dismissal and old rule versions. No job is created for an external effect.

- [ ] T1 | slice=mission_control | files=mission_control/migrations/0003_rule_proposals.sql,mission_control/automation_proposals.py,mission_control/schema_types.py | verify=`python -m unittest tests.test_automation_proposals -q` | Retain app and owner scoped rule evaluation, inbox proposals and non-executing review decisions with persistent deduplication.
- [ ] T2 | slice=mission_control | files=mission_control/automation_proposal_schedule.py,mission_control/worker.py,mission_control/automation_health.py | verify=`python -m unittest tests.test_automation_proposal_schedule -q` | Bind finite local schedule and make one due-slot write replay-safe, with race and restart proof.
- [ ] T3 | slice=mission_control | files=mission_control/server.py,mission_control/static/app-campaign.mjs,mission_control/static/app-events.mjs | verify=`python -m unittest tests.test_automation_rules_browser -q` | Expose Results inbox and finite scheduling with current owner checks, meaningful statuses, and explicit review controls.
- [ ] T4 | slice=tests | files=tests/test_automation_proposals.py,tests/test_automation_proposal_schedule.py,tests/test_automation_rules_browser.py | verify=`python -m unittest tests.test_automation_rules tests.test_automation_proposals tests.test_automation_proposal_schedule tests.test_automation_rules_browser -q` | Prove auth isolation, read-only preview, stale authority denial, bounds, deduplication, recovery and accessible Results.

Proof stays separate from live provider or host acceptance. Update the P1/P2 delivery status only to the extent the corresponding functionality is proven.

