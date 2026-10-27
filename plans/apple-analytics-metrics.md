# Plan: apple-analytics-metrics
Spec: specs/apple-analytics-metrics.md. User authorized private per-account reads.
Architect verdict: PASS - staged contract; signed segment transport is bounded and tested, while correction-aware reconciliation remains an explicit, unverified T3 acceptance task.

- [x] T1 | slice=specs | files=specs/apple-analytics-metrics.md | verify=`specline strict apple-analytics-metrics --root . --json` | Bind scope, integrity, reconciliation and explicit unknowns before implementation.
- [x] T2 | slice=mission_control | files=mission_control/apple_analytics.py,mission_control/providers.py,mission_control/apple_segments.py | verify=`python -m unittest tests.test_apple_metrics_transport -v` | Traverse scoped segments and download bounded verified bytes without credential or signed URL leakage.
- [ ] T3 | slice=mission_control | files=mission_control/apple_metrics.py,mission_control/apple_metrics_store.py,mission_control/db.py | verify=`python -m unittest tests.test_apple_metrics -v` | Validate supported report schemas and retain app-scoped provenance with idempotent correction-aware reconciliation.
- [ ] T4 | slice=tests | files=tests/test_apple_metrics_transport.py,tests/test_apple_metrics.py | verify=`python -m unittest tests.test_apple_metrics_transport tests.test_apple_metrics -v` | Exercise malformed, foreign, duplicate, partial, delayed and corrected synthetic reports.
- [ ] T5 | slice=mission_control | files=mission_control/provider_reports.py,mission_control/worker.py,mission_control/apple_metrics_schedule.py | verify=`python -m unittest tests.test_apple_metrics_worker -v` | Connect durable per-app refresh, bounded retries and recovery to existing authority checks.
- [ ] T6 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/app.css,mission_control/operation_runtime.py | verify=`python -m unittest tests.test_apple_metrics_surface -v` | Present observations, coverage and recovery for owners and admitted agents.
- [ ] T7 | slice=tests | files=tests/test_apple_metrics_worker.py,tests/test_apple_metrics_surface.py | verify=`python -m unittest tests.test_apple_metrics_worker tests.test_apple_metrics_surface -v` | Verify scheduled recovery and authorized surface readback.
- [ ] T8 | slice=plans | files=plans/apple-analytics-metrics.md | verify=`specline gate plan apple-analytics-metrics --approver codex-user-authorized --root .` | Keep provider and complete product acceptance distinct from synthetic tests.

Packet order must be refined against actual existing workers and surfaces before
implementation; no assumed file or interface above claims that code exists.
Current provider data is private and may not yet include any report instance.
No actual metric, app outcome or provider/device acceptance is claimed.
The local transport packet passed 62 Apple analytics, parser, contract, store,
and segment-transport tests on Windows/Python 3.11.9. Apple's documented S3 sample
host pattern is the only accepted signed destination shape; provider endpoints,
credentials and live report instances remain unverified and are NOT_RUN.
