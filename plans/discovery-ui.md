# Plan: discovery-ui
Spec: specs/discovery-ui.md
Architect verdict: PASS

- [x] T1 | slice=mission_control | files=mission_control/static/discovery-model.js | verify=`node --test tests/discovery_ui.test.cjs` | Build closed structured review query decision and report models using explicit observed facts.
- [x] T2 | slice=mission_control | files=mission_control/static/discovery-ui.js,mission_control/static/app.js,mission_control/static/style.css | verify=`node --test tests/discovery_ui.test.cjs tests/ui_stories.test.cjs` | Integrate owner forms immutable browsing scope invalidation unknown write reconciliation and reports.
- [x] T3 | slice=tests | files=tests/discovery_ui.test.cjs | verify=`node --test tests/discovery_ui.test.cjs` | Prove boundary filters errors exports privacy late responses and duplicate request handling with actual model/controller code.
- [x] T4 | slice=smoke | files=smoke/discovery-ui.json | verify=`forge smoke discovery-ui --root .` | Verify actual owner browser and source-bound non-hollow model checks before delivery.

- [x] T5 | slice=mission_control | files=mission_control/static/index.html,mission_control/static/ui-stories.js,mission_control/server.py | verify=`node --test tests/ui_stories.test.cjs` | Serve exact new scripts and register task explanations in existing shared story catalog.

Scoped source-review/collection UI and exports implemented with actual owner browser source authoring, lost-response reconciliation, app-switch clearing, desktop/mobile no-overflow and PDF/JSON/CSV proof. Watch/attempt UI, brief/editor/Hypit handoff consumption, actual authorized collectors/schedules, native iOS and full platform acceptance remain required parent work.
