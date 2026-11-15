# Plan: surface-stopped-rule-schedules
Spec: specs/surface-stopped-rule-schedules.md
Architect verdict: PASS

Use a shared exception card constructor and bounded projection in the existing owner membership snapshot. The recovery action uses the current weekly review identity and the existing read-only Results inbox. No new API or change to worker behavior.

- [ ] T1 | slice=mission_control | files=mission_control/weekly_inbox.py,mission_control/weekly_rule_exception.py,mission_control/weekly_exception_card.py | verify=`python -B -m unittest tests.test_weekly_rule_exception -q` | Report private rule schedule failures without exposing stored rule data.
- [ ] T2 | slice=mission_control | files=mission_control/static/app-weekly.mjs | verify=`node --test tests/weekly_operation_ui.test.cjs` | Open the exact current app's saved recommendations from a valid private exception.
- [ ] T3 | slice=tests | files=tests/test_weekly_rule_exception.py,tests/weekly_operation_ui.test.cjs | verify=`python -B -m unittest tests.test_weekly_rule_exception -q` | Check real workspace boundaries and assert read-only navigation.

## Corrective scope

1. Modify `mission_control/weekly_rule_exception.py`: isolate unexpected projection failures into a generic owner-only Results card with status-only evidence, without returning exception details. Keep `mission_control/weekly_inbox.py`'s existing app membership and table guards; unrelated findings and active work must remain available.
2. Modify `mission_control/weekly_rule_exception.py`: for an ACTIVE row owned by this principal, test expiry against the current time and exhaustion against the bounded run limit before parsing the saved definition. Preserve explicit BLOCKED rows and use only fixed reason strings. No storage writes or changes to approval, worker behavior, routes, or client presentation.
3. Modify `tests/test_weekly_rule_exception.py`: exercise corrupt definitions on expired and exhausted ACTIVE rows; simulate a schedule read failure and assert the other operational card remains and the new error is private and redacted. Re-run the weekly and schedule tests and the existing read-only UI navigation test.
