# Plan: always-on-rule-integration
Spec: specs/always-on-rule-integration.md
Architect verdict: PASS

Use one exact report reference and the existing owner report transaction. Keep the saved schedule and runtime receipt as the source of truth. No provider commands, dynamic dispatch, new operation, database migration or separate scheduler.

- [ ] T1 | slice=mission_control | files=mission_control/automation_rule_report_integration.py,mission_control/automation_proposal_schedule.py,mission_control/automation_proposals.py | verify=`python -m unittest tests.test_automation_rule_report_integration -q` | Bind consent, run the exact report action once and stop on current authority drift.
- [ ] T2 | slice=mission_control | files=mission_control/static/automation-proposal-inbox.mjs,mission_control/static/app-campaign.mjs | verify=`python -m unittest tests.test_automation_rules_browser -q` | Show the selectable private report, bounded approval and inspectable outcome.
- [ ] T3 | slice=tests | files=tests/test_automation_rule_report_integration.py,tests/test_automation_rules_browser.py | verify=`python -m unittest tests.test_automation_rule_report_integration tests.test_automation_proposal_schedule tests.test_automation_rules_browser -q` | Exercise real local persistence, drift, retry, expiry and the owner flow.
- [ ] T4 | slice=docs | files=docs/AUTOMATION-LOGIC.md | verify=`specline strict always-on-rule-integration` | Explain opt-in, fixed dates and the one private save per approval.

## Detailed Implementation Plan

Consent accepts an optional report_integration object with report_id and report_hash. The worker pins the source fingerprint and derives a private capture_key from the app, owner, exact next schedule version, rules and report. A selected study and report must share dates. The report may describe independently selected campaign evidence; matching dates do not establish attribution. Old schedules have no integration field.

Under BEGIN IMMEDIATE the worker rechecks owner role, app and saved versions, study and report binding. In the evaluation savepoint it selects only the closed Results action after a complete match and ordinary dismissal/cooldown checks. Use the existing report capture once under the private key. Store REPORT_SAVED with proposal ID, report ID and fingerprint in the run or NO_NEW_MATCH when there is no qualifying change. Recheck expiry and advance inside the same transaction so the report, receipt and due slot commit together. Existing report source status describes delivery evidence, while current schedule and owner state authorize private storage.

Results shows report dates before confirmation, says the approval saves one private report, and uses the indexed capture key to verify its ID and fingerprint after later evaluations. The private reports view provides the report body. Tests exercise existing recommendations, cooldown, mixed missing data, unrelated fact changes, selected study dates, two workers, restart, tampered template and expiry after the save, then verify the active stop action through the browser.
