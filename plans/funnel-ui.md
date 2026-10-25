# Plan: funnel-ui
Spec: specs/funnel-ui.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control/static | files=mission_control/static/funnel-model.js | verify=`node --test tests/funnel_ui.test.cjs` | Implement explicit plan observation result and export models with bounded graph and source inputs.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/funnel-ui.js,mission_control/static/app.js,mission_control/static/index.html,mission_control/static/ui-stories.js | verify=`node --test tests/funnel_ui.test.cjs tests/ui_stories.test.cjs` | Add scoped owner workflows with preserved drafts, explicit narratives and exact uncertain-write recovery.
- [ ] T3 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_funnel_ui_http -v` | Serve only the named local UI modules and retain exact owner routes.
- [ ] T4 | slice=tests | files=tests/funnel_ui.test.cjs,tests/test_funnel_ui_http.py | verify=`node --test tests/funnel_ui.test.cjs` | Verify source bindings unknown/zero reports escaping pages pending writes and context changes.
- [ ] T5 | slice=tools | files=tools/test_funnel_ui_browser.py | verify=`python -X utf8 tools/test_funnel_ui_browser.py` | Exercise real owner HTTP desktop/mobile creation import recovery pagination and PDF JSON CSV exports.
- [ ] T6 | slice=smoke | files=smoke/funnel-ui.json | verify=`forge smoke funnel-ui --root .` | Prove runtime UI models reject an inert implementation and actual served workflows pass.
