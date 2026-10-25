# Plan: managed-media-stitch
Spec: specs/managed-media-stitch.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/managed_media_store.py,mission_control/video_edit_contract.py,mission_control/video_edit_projects.py | verify=`python -m unittest tests.test_managed_media_stitch -v` | Bind immutable source snapshots and distinct source kinds while retaining legacy native bytes.
- [ ] T2 | slice=mission_control | files=mission_control/video_edit_rendering.py,mission_control/video_edit_jobs.py | verify=`python -m unittest tests.test_managed_media_stitch -v` | Normalize frame timing and render ordered clips with selected retained or muted audio and guarded commit.
- [ ] T3 | slice=mission_control/static | files=mission_control/static/video-editor.js,tests/video_editor.test.cjs | verify=`node --test tests/video_editor.test.cjs` | Expose reviewed uploaded footage and sound selection through existing shared project controls.
- [ ] T4 | slice=tests | files=tests/test_managed_media_stitch.py | verify=`python -m unittest tests.test_managed_media_stitch -v` | Prove real multi-clip video/audio, revoked/stale source rejection and shared agent operation parity.

Original media remains preserved; no full Hypit, Drive, funnel or goal completion claim.
