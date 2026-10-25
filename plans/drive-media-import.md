# Plan: drive-media-import
Spec: specs/drive-media-import.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/drive_media_contract.py,mission_control/drive_media_transport.py | verify=`python -m unittest tests.test_drive_media -v` | Verify exact selected metadata and bounded fixed-host original download with checksum and version checks.
- [ ] T2 | slice=mission_control | files=mission_control/drive_media.py,mission_control/managed_media_store.py | verify=`python -m unittest tests.test_drive_media tests.test_managed_media_store -v` | Guard current account/selection/connection and immutably ingest provider provenance through decoded media validation.
- [ ] T3 | slice=tests | files=tests/test_drive_media.py | verify=`python -m unittest tests.test_drive_media tests.test_drive_accounts tests.test_managed_media_stitch -v` | Prove actual source bytes, reuse/editor selection, replay, disconnect and changed-source denial.
- [ ] T4 | slice=smoke | files=smoke/drive-media-import.json | verify=`forge smoke drive-media-import --root .` | Require non-hollow metadata and provenance assertions plus actual import lifecycle tests.
