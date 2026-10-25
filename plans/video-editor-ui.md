# Plan: video-editor-ui
Spec: specs/video-editor-ui.md
Architect verdict: PASS

## Architecture
One browser module calls existing project/render APIs and preserves exact revision
and app identity. No new execution backend or local storage preference. Human and
agent edits share the authoritative service; pending/dirty/stale UI checks improve
recovery and never replace server validation. Reports reuse existing PDF engine.

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/video-editor.js | verify=`node --test tests/video_editor.test.cjs` | Implement editor_human, editor_controls and editor_recovery with exact shared APIs.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/static/ui-stories.js,mission_control/static/video-editor.css | verify=`node --test tests/video_editor.test.cjs tests/ui_stories.test.cjs` | Wire editor_media, current source controls and editor_report guidance into the existing page/modal lifecycle with scoped readable control groups.
- [ ] T3 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_video_editor_http -v` | Serve the fixed editor_human asset through the existing local boundary.
- [ ] T4 | slice=tests | files=tests/video_editor.test.cjs,tests/test_video_editor_http.py | verify=`node --test tests/video_editor.test.cjs tests/ui_stories.test.cjs` | Test editor_controls proposals, report privacy and exact source hooks alongside actual desktop/mobile browser acceptance.

## Gates
CF strict/five requirement mutants, task/spec/plan, source mutations, current tests,
real desktop/mobile create/edit/history/render/media/report/recovery observations,
Prestige deterministic audits and hash-bound workflow evidence. Full editor and
marketer goal remain incomplete until every required control/workflow is proven.
