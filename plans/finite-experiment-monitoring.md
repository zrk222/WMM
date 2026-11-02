# Plan: finite-experiment-monitoring
Spec: specs/finite-experiment-monitoring.md
Architect verdict: PASS

## Architecture
A separate finite authorization row binds owner, app and immutable experiment while preserving the existing schedule and jobs. Admission, reservation and queue insertion share the existing SQLite write transaction; assessment rechecks retained authority inside the existing evaluator transaction. Legacy and restored schedules are paused. Local observations never grant external effects.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/experiment_schedules.py,mission_control/db.py,tests/test_schedules.py | verify=`python -m pytest -q tests/test_schedules.py` | Bind and enforce finite schedule reservations and recovery.
- [ ] T2 | slice=mission_control | files=mission_control/server.py,mission_control/automation_health.py,tests/test_experiment_schedule_http.py,tests/test_http.py | verify=`python -m pytest -q tests/test_experiment_schedule_http.py tests/test_http.py` | Protect owner admission and project exact schedule state.
- [ ] T3 | slice=mission_control/static | files=mission_control/static/app.js,tests/experiment_schedule_ui.test.cjs | verify=`node --test tests/experiment_schedule_ui.test.cjs` | Show finite limits, remaining runs and local-only scope.
- [ ] T4 | slice=ios/WMM | files=ios/WMM/Workflow/NativeWorkspaceModel.swift,ios/WMM/Workflow/WorkflowNavigation.swift,ios/WMM/Agents/NativeAutomationView.swift,tests/test_ios_experiment_monitoring.py | verify=`python -m pytest -q tests/test_ios_experiment_monitoring.py` | Integrate the existing embedded bridge and foreground schedule controls.

## Gates
Run strict, validator mutation, challenge and spec and plan seals before implementation. Exercise synthetic isolated recovery, HTTP authorization and UI races; native iPhone and iPad acceptance requires actual simulator CI evidence.
