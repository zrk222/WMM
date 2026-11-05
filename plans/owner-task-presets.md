# Plan: owner-task-presets
Spec: specs/owner-task-presets.md
Architect verdict: PASS for UI preparation over existing server grants; whole goal remains open.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/static/agent-control.js | verify=`node --test tests/agent_control.test.cjs tests/agent_task_presets.test.cjs` | Fixed task/effect contracts, catalog validation, concise summary, optional advanced scope and field-preserving explicit selection.
- [ ] T2 | slice=tests | files=tests/agent_task_presets.test.cjs,tests/test_agent_task_presets.py | verify=`python -m unittest tests.test_agent_task_presets` | Real catalog effect parity, unsupported/custom/read-only boundaries, zero automatic authority and existing issue validation.
- [ ] T3 | slice=tools | files=tools/test_agent_task_presets_browser.py | verify=`python tools/test_agent_task_presets_browser.py` | Synthetic actual-browser owner flow at desktop/mobile with keyboard, preserved dates, optional advanced controls, unavailable states and no job/effect on selection.
- [ ] T4 | slice=docs | files=docs/agent-grants.md | verify=`python tools/check_distribution.py` | Explain task presets versus actual grants and exact campaign approvals, total calls and advanced customization without claiming end-to-end automation.

## Gate notes
Keep PR113 source frozen while its remaining native/package gates run. This successor branch starts from its exact repair head; it is not merged or published until independently reviewed and tested. Use CF doctor, SpecLine strict/mutations/task seal, deterministic UI checks and hash-bound workflow evidence. No live account changes.
