# Plan: ui-storytelling
Spec: specs/ui-storytelling.md
Architect verdict: PASS

## Architecture
Use an explicit page/form narrative registry and a text-escaped renderer. Page
report decoration adds page context after its current heading. Shared modal
decoration identifies form IDs from static application markup; it never reads
input values or intercepts controls. Unknown/read-only dialogs receive an
inspection orientation with no invented action effect. Test the registry against
the actual navigation/form source inventory so future omissions fail visibly.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/static/ui-stories.js,mission_control/static/page-reporting.js,mission_control/static/app.js,mission_control/static/index.html | verify=`node --test tests/ui_stories.test.cjs` | Implement page_stories and dialog_stories with shared lifecycle hooks.
- [ ] T2 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_ui_stories_http -v` | Serve the exact narrative asset without a new authority surface.
- [ ] T3 | slice=tests | files=tests/ui_stories.test.cjs,tests/test_ui_stories_http.py | verify=`node --test tests/ui_stories.test.cjs tests/page_reporting.test.cjs` | Prove actual source inventory coverage, escaping, no private-field reads and preserved controls.

## Gates
CF doctor, strict requirement mutations and pre-code seals; Node and HTTP tests,
actual ten-page desktop/mobile and dialog flows, Prestige audits and hash-bound
workflow evidence. Parent automation toggle and full-domain feature work remain
required and are not completed by copy changes.
