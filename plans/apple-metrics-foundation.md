# Plan: apple-metrics-foundation
Spec: specs/apple-metrics-foundation.md. Parent: plans/apple-analytics-metrics.md.
Architect verdict: PASS - local foundation only; live transport remains disabled pending a separate host and network security review.

- [ ] T1 | slice=mission_control | files=mission_control/apple_metrics_contract.py,mission_control/apple_metrics_store.py,mission_control/db.py | verify=`python -m unittest tests.test_apple_metrics_store -q` | Add app/source/report/granularity partitions and atomic dated reconciliation.
- [ ] T2 | slice=tests | files=tests/test_apple_metrics_contract.py,tests/test_apple_metrics_store.py | verify=`python -m unittest tests.test_apple_metrics_contract tests.test_apple_metrics_store tests.test_apple_analytics_parser -q` | Cover bounded contract validation, conflicting versions, duplicates, rollback and cross-app isolation.
- [ ] T3 | slice=mission_control | files=mission_control/apple_metrics_schedule.py,mission_control/apple_metrics_worker.py,mission_control/worker.py,mission_control/db.py | verify=`python -m unittest tests.test_apple_metrics_worker tests.test_apple_metrics_schedule -q` | Add default-paused schedule, fenced job execution, disabled transport and retry outcomes.
- [ ] T4 | slice=tests | files=tests/test_apple_metrics_worker.py,tests/test_apple_metrics_schedule.py,tests/test_apple_metrics_transport.py | verify=`python -m unittest tests.test_apple_metrics_worker tests.test_apple_metrics_schedule tests.test_apple_metrics_transport -q` | Prove lease, revocation, restart and zero-network disabled transport.
- [ ] T5 | slice=mission_control | files=mission_control/service.py,mission_control/server.py,mission_control/operation_runtime.py | verify=`python -m unittest tests.test_apple_metrics_surface -q` | Expose authorized readback and recovery without secret or authority export.
- [ ] T6 | slice=tests | files=tests/test_apple_metrics_surface.py | verify=`python -m unittest tests.test_apple_metrics_surface tests.test_schedules -q` | Verify cross-app denial, restored pause and source-bound recovery.
- [ ] T7 | slice=specs | files=specs/apple-metrics-foundation.md | verify=`specline strict apple-metrics-foundation --root . --json` | Bind local acceptance and live transport exclusion.
- [ ] T8 | slice=plans | files=plans/apple-metrics-foundation.md | verify=`specline tasks apple-metrics-foundation --root .` | Preserve parent report-family, provider and outcome requirements.

Every observation transaction must revalidate the current app, source, schedule,
job attempt and lease plus applicable authority. Successful ingestion and job
completion must be committed atomically or use an explicitly recoverable two-phase
protocol. Synthetic adapters must not be reachable from external input. Error
states distinguish disabled, waiting, empty, partial and failed reads from success.
