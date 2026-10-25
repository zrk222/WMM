# Plan: studio-control-ui
Spec: specs/studio-control-ui.md
Architect verdict: PASS

## Architecture
One isolated UI module over existing protected same-origin Studio endpoints.
Keep app/version/dialog generation and one in-flight action, disable mutation
after ambiguous result, and preserve request keys. Typed compiled controls use
native inputs or explicit JSON editors for structured values. Reuse existing
modal, narration, reporting and creative-workspace hooks. No native-origin iframe.

## Tasks
- [x] T1 | slice=mission_control/static | files=mission_control/static/studio-controls.js | verify=`node --test tests/studio_controls.test.cjs` | Implement studio_summary, studio_fields, studio_edit, studio_unknown, studio_scope and studio_history.
- [x] T2 | slice=mission_control/static | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/static/ui-stories.js | verify=`node --test tests/ui_stories.test.cjs tests/studio_controls.test.cjs` | Wire existing workspace, modal cleanup and task narration.
- [x] T3 | slice=tests | files=tests/studio_controls.test.cjs | verify=`node --test tests/studio_controls.test.cjs` | Prove types escaping request identity pending action and stale-response handling.
- [x] T4 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_hypit_studio_clients -q` | Serve only the exact new static module through the existing fixed allowlist.

## Gates
CF strict/validator/tasks, meaningful Node tests and guard mutations, real desktop
and mobile keyboard/focus flows, actual authenticated synthetic HTTP/installed
Studio edit readback, prescribed Prestige checks, privacy and workflow audit.
Full source/semantic editing, isolated native preview and edited-project render
integration remain required parent work, not implemented by a parameter form.

## Scoped verification - October 25, 2026
All compiled control types, exact startup summary, source-bound edits, unknown
outcome pause, terminal cleanup, observed coverage and PDF report controls are
implemented for existing approved caption compositions. Current Node and protected
HTTP checks, three rejected code mutants, desktop/mobile keyboard and PDF flows,
and installed Hypit browser-edit/agent-readback evidence are retained under
.factory/studio-control-ui. The original stale-reply test allowed an identical
replacement dialog; the repaired test checks replacement count and principal
changes, and rejects the deleted guard. Earlier failed checks remain retained.

The installed probe uses a synthetic authenticated provider identity and actual
local Hypit, not a real user's production account. This scoped UI proof does not
close the parent transport's pending independent/static analysis, whole-product
regression, restart reconciliation, isolated preview, semantic source editing,
imported media, Drive, autonomous discovery or edited-project final render.
No merge, deployment, paid action or public publication is performed.
