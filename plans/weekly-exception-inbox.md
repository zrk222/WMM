# Plan: weekly-exception-inbox
Spec: specs/weekly-exception-inbox.md
Architect verdict: PASS

Architecture: GET /api/weekly-review?offset=N uses the existing Service workspace
reader for at most five saved apps per page. Each workspace is projected into
four prerequisite exceptions plus confirmed P0 findings; failures become a
redacted unavailable card. No credential or provider operation is introduced.
Response reports total app count, next offset and source hashes. UI uses an
explicit refresh/loading/error state and existing guidedOpenTool routes after
awaiting the selected app refresh; a navigation generation rejects stale replies.
Keep the existing app navigation layout and add Weekly review before Overview.
Reuse panels/buttons/details and visible-focus styles; no decorative hero.

- [x] T1 | slice=mission_control | files=mission_control/weekly_inbox.py | verify=`python -m unittest tests.test_weekly_inbox -q` | Build read-only app-bound exception projection with explicit source failures and authority denial.
- [x] T2 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_weekly_inbox_http -q` | Expose bounded portfolio review through existing loopback boundaries.
- [x] T3 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/index.html | verify=`python tools/test_weekly_inbox_browser.py` | Render exception review and safe app-bound recovery using existing controls and unchanged shared styles.
- [x] T4 | slice=tests | files=tests/test_weekly_inbox.py,tests/test_weekly_inbox_http.py | verify=`python -m unittest discover -s tests -q` | Prove isolation, unknown/source failures, coverage, no execution and regressions.
- [x] T5 | slice=tools | files=tools/test_weekly_inbox_browser.py | verify=`python tools/test_weekly_inbox_browser.py` | Verify desktop/mobile keyboard, exact app routing, source-error visibility and stale response denial.

Before implementation: strict/validator/spec/plan gates, reviewed architecture,
Prestige design contract and full scoped workflow applicability. After source:
browser observations, deterministic design audits, regression, privacy scan and
hash-bound CF workflow gate. No provider-side campaign claim from fixtures.
