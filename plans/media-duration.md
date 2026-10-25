# Plan: media-duration
Spec: specs/media-duration.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/video_edit_rendering.py | verify=`python -m unittest tests.test_media_duration -v` | Compile a fixed AAC priming correction at final concat mux without weakening imported-media validation.
- [ ] T2 | slice=tests | files=tests/test_media_duration.py | verify=`python -m unittest tests.test_media_duration tests.test_managed_media_stitch tests.test_video_edit_render tests.test_managed_media_validation -v` | Prove real60-second single/stitch decode and sound, strict limits, unchanged mute and current source rights.
- [ ] T3 | slice=smoke | files=smoke/media-duration.json | verify=`forge smoke media-duration --root .` | Require non-hollow mux compilation and real source/job/render acceptance before scoped completion.
