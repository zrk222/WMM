# Plan: agent-control-ui
Spec: specs/agent-control-ui.md
Architect verdict: PASS

## Architecture
Add a separate UMD presentation/controller module. Read operation discovery from the existing catalog route. Use owner-only grant endpoints and separate human-review endpoints. Reuse existing signed review sessions and native report preview. Hold response data on the current dialog only; credentials exist only in the once-only password control and are erased on scope changes. The authoritative service enforces roles, currentness, revision and distinct-checker boundaries.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/static/agent-control.js,tests/agent_control.test.cjs | verify=`node --test tests/agent_control.test.cjs` | Implement grant_controls, secret_delivery, review_queue, exact_review, reconciliation, scope_safety and reports.
- [x] T2 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/server.py,tests/test_agent_control_ui.py | verify=`python -m unittest tests.test_agent_control_ui -v` | Implement integration with static allowlist, existing views and scope invalidation.
- [x] T3 | slice=tools | files=tools/test_agent_control_browser.py | verify=`python tools/test_agent_control_browser.py` | Prove real browser integration at desktop and mobile, independent checker approval, errors, paging and PDF privacy.

- [x] T4 | slice=mission_control | files=mission_control/agent_operations.py | verify=`python -m unittest tests.test_agent_control_ui -v` | Return the existing fixed operation catalog in app discovery for grant selection without granting execution authority.

## Acceptance
Run scoped CF gates, source mutations, actual browser/PDF acceptance, prescribed Prestige audits and hash-bound project-neutral workflow QA. Retain failing observations and preserve unrelated files. No full-product completion or real provider acceptance claim follows from this scoped packet.
