# Plan: managed-media-ui
Spec: specs/managed-media-ui.md
Architect verdict: PASS

## Architecture
One dependency-injected static module over exact same-origin media routes.
Reuse shared modal/reporting/native video elements and existing design classes.
Capture app/version/principal/dialog identity, one pending mutation and scoped
unknown-upload hashes; local hashing enables saved-source readback comparison.
File batches execute sequentially and stop on uncertainty; no retry loop.

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/managed-media.js | verify=`node --test tests/managed_media.test.cjs` | Implement media_upload, media_inspect, media_rights, media_scope, media_report and media_access.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/static/ui-stories.js | verify=`node --test tests/managed_media.test.cjs` | Wire Research entrypoint, exact script, submit/action and stale modal cleanup.
- [ ] T3 | slice=tests | files=tests/managed_media.test.cjs | verify=`node --test tests/managed_media.test.cjs` | Prove bounded sequential file intake, escaping, rights/source identity, scope invalidation and uncertain no-resend.

## Gates
CF strict/validator/tasks/drift, focused tests and hash-bound workflow evidence.
After root API confirmation run actual HTTP upload/rights/playback/download,
desktop/mobile keyboard smoke, privacy and prescribed Prestige deterministic
checks. Nanna mission: preserve selected footage; tension: reuse remains unknown;
guidance: inspect bytes and provenance; agency: attest or revoke; payoff: saved
state and original download; next action: inspect current rights before editing.
