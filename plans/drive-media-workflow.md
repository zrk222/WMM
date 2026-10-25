# Plan: drive-media-workflow
Spec: specs/drive-media-workflow.md
Architect verdict: PASS; requirements decomposition reviewed, implementation gates pending

- [ ] T1 | slice=mission_control | files=mission_control/drive_auth.py,tests/test_drive_auth.py | verify=`python -m unittest tests.test_drive_auth -v` | Prove fixed selected-file consent and strict callback, scope and PKCE validation with negative mutants.
- [ ] T2 | slice=mission_control | files=mission_control/drive_secrets.py,tests/test_drive_secrets.py | verify=`python -m unittest tests.test_drive_secrets -v` | Reuse protected credential lifecycle and namespace isolation without plaintext fallback.
- [ ] T3 | slice=mission_control | files=mission_control/drive_connections.py,tests/test_drive_connections.py | verify=`python -m unittest tests.test_drive_connections -v` | Persist app-bound one-use flows, account replacement review and cancellation without losing a working connection.
- [ ] T4 | slice=mission_control | files=mission_control/drive_media.py,tests/test_drive_media.py | verify=`python -m unittest tests.test_drive_media -v` | Verify bounded selected-file downloads and immutable managed-source provenance through actual decoded media.
- [ ] T5 | slice=mission_control | files=mission_control/drive_http.py,tests/test_drive_http.py | verify=`python -m unittest tests.test_drive_http -v` | Wire owner-only setup, callback, selection, import and disconnect through existing origin and session guards.
- [ ] T6 | slice=mission_control | files=mission_control/drive_operations.py,tests/test_drive_clients.py | verify=`python -m unittest tests.test_drive_clients -v` | Register credential-redacted shared CLI and official MCP selection and job controls.
- [ ] T7 | slice=mission_control | files=mission_control/static/drive-media.js,tests/js/test_drive_media.js | verify=`node --test tests/js/test_drive_media.js` | Add optional onboarding and selection UI with source health, reuse review and recovery alongside local upload.
- [ ] T8 | slice=mission_control | files=mission_control/drive_automation.py,tests/test_drive_automation.py | verify=`python -m unittest tests.test_drive_automation -v` | Enforce selected-library autonomous grants, credential readiness, limits, expiry and revocation throughout worker stages.
- [ ] T9 | slice=mission_control | files=mission_control/drive_reports.py,tests/test_drive_reports.py | verify=`python -m unittest tests.test_drive_reports -v` | Connect actual job telemetry and source metrics to PDF and data reports without fabricating unknown cost or outcome values.
- [ ] T10 | slice=tests | files=tests/test_drive_acceptance.py | verify=`python -m unittest tests.test_drive_acceptance -v` | Exercise source import, shared editing, actual decoded stitching, owner and agent autonomy, browser and keyboard proof, and provider acceptance boundaries.

File names identify proposed ownership boundaries; architecture review must resolve
existing registration, schema and editor extension points before each packet.
Existing source files needed for wiring belong in each packet's candidate hash set.
Transitions, sound-level controls, images and cross-platform credential protection
remain explicit dependent work; they cannot be waived by passing Drive fixtures.
The full WMM goal remains ACTIVE INCOMPLETE until all accepted workflows pass.
