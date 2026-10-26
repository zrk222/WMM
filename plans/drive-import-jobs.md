# Plan: drive-import-jobs
Spec: specs/drive-import-jobs.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/drive_import_jobs.py,mission_control/drive_media.py | verify=`python -m unittest tests.test_drive_import_jobs -v` | Freeze owner/source/namespace job authority, actual stage events, guarded cancellation and exact committed-source recovery.
- [ ] T2 | slice=mission_control | files=mission_control/worker.py,mission_control/service.py,mission_control/workflow_telemetry.py | verify=`python -m unittest tests.test_drive_import_jobs tests.test_worker tests.test_workflow_telemetry -v` | Reuse durable worker dispatch and private event codes while keeping generic public histories and cancellation outside Drive authority.
- [ ] T3 | slice=tests | files=tests/test_drive_import_jobs.py | verify=`python -m unittest tests.test_drive_import_jobs tests.test_drive_media -v` | Prove actual queued import, replay, source/stage proof, owner changes, cancellation and interrupted-result recovery.
- [ ] T4 | slice=smoke | files=smoke/drive-import-jobs.json | verify=`forge smoke drive-import-jobs --root .` | Require non-hollow job authority and actual worker acceptance checks before scoped delivery.
