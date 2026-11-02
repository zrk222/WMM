# Plan: apple-metrics-waiting
Spec: specs/apple-metrics-waiting.md
Architect verdict: PASS

## Architecture
An empty latest-instance selection returns the existing prepared result type with an empty immutable partition tuple. Its closed waiting summary passes through the existing worker lease, schedule and source checks. The scheduler validates the entire waiting summary against current job and source before treating the read as successful without numeric ingestion.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/provider_reports.py,mission_control/apple_metrics_schedule.py | verify=`python -m unittest tests.test_apple_metrics_schedule tests.test_apple_metrics_schedule_selection -v` | Carry and reconcile source-bound waiting observations.
- [ ] T2 | slice=tests | files=tests/test_apple_metrics_schedule.py,tests/test_apple_metrics_schedule_selection.py | verify=`python -m unittest tests.test_apple_metrics_schedule tests.test_apple_metrics_schedule_selection -v` | Exercise repeated waiting, stale sources, malformed waiting and genuine failures.

## Gates
Strict spec, validator mutation, plan lint, focused worker and schedule regression and hash-bound workflow evidence. Real provider and real account acceptance remain separate.
