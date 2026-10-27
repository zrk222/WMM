# Plan: apple-analytics-metrics
Spec: specs/apple-analytics-metrics.md. User authorized private per-account reads.
Architect verdict: PASS - T1-T4 now have local, hash-bound evidence for bounded segment transport, supported downloads parsing, offline correction-aware reconciliation, and adversarial synthetic cases. Durable scheduled ingestion, additional report families, user-facing surfaces, and live account acceptance remain incomplete.

- [x] T1 | slice=specs | files=specs/apple-analytics-metrics.md | verify=`specline strict apple-analytics-metrics --root . --json` | Bind scope, integrity, reconciliation and explicit unknowns before implementation.
- [x] T2 | slice=mission_control | files=mission_control/apple_analytics.py,mission_control/providers.py,mission_control/apple_segments.py | verify=`python -m unittest tests.test_apple_metrics_transport -v` | Traverse scoped segments and download bounded verified bytes without credential or signed URL leakage.
- [x] T3 | slice=mission_control | files=mission_control/apple_metrics.py,mission_control/apple_metrics_store.py,mission_control/db.py,tests/test_apple_metrics.py | verify=`python -m unittest tests.test_apple_metrics tests.test_apple_metrics_store tests.test_apple_metrics_contract tests.test_apple_analytics_parser tests.test_apple_metrics_transport -v` | Validate the supported downloads schema, split complete instances by observation date, and retain app-scoped provenance with atomic, idempotent correction-aware reconciliation.
- [x] T4 | slice=tests | files=tests/test_apple_metrics_transport.py,tests/test_apple_metrics.py | verify=`python -m unittest tests.test_apple_metrics_transport tests.test_apple_metrics -v` | Exercise malformed, foreign, duplicate, partial, delayed and corrected synthetic reports.
- [x] T5 | slice=mission_control | files=mission_control/provider_reports.py,mission_control/worker.py,mission_control/marketing_agent_manifest.py,tests/test_apple_metrics_worker.py | verify=`python -m unittest tests.test_apple_metrics_worker -v` | Read a user-selected complete downloads instance through the existing bounded provider read, permitted agent operation and leased job; atomically persist app-scoped observations with job completion.
- [x] T6 | slice=specs | files=specs/apple-analytics-metrics.md | verify=`specline strict apple-analytics-metrics --root . --json` | Specify owner opt-in, newest complete daily report selection, bounded retries and connection-change recovery.
- [x] T7 | slice=mission_control | files=mission_control/provider_reports.py,mission_control/marketing_agent_manifest.py,tests/test_apple_metrics_schedule_selection.py | verify=`python -m unittest tests.test_apple_metrics_schedule_selection -v` | Resolve the newest complete daily downloads instance deterministically for owner-enabled scheduled reads while preserving T5's exact-instance selection.
- [ ] T8 | slice=mission_control | files=mission_control/apple_metrics_schedule.py,mission_control/db.py,mission_control/worker.py,tests/test_apple_metrics_schedule.py | verify=`python -m unittest tests.test_apple_metrics_schedule -v` | Add an owner-opt-in app-scoped refresh schedule with durable status, bounded retries, lease fencing and current app/connection recovery.
- [ ] T9 | slice=mission_control | files=mission_control/store.py,tests/test_apple_metrics_schedule.py | verify=`python -m unittest tests.test_apple_metrics_schedule -v` | Export schedule status without credential material and restore it paused with no copied active-job authority.
- [ ] T10 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/app.css,mission_control/operation_runtime.py,tests/test_apple_metrics_surface.py | verify=`python -m unittest tests.test_apple_metrics_surface -v` | Present observations, freshness, coverage, owner schedule controls and recovery to owners and admitted agents.
- [ ] T11 | slice=tests | files=tests/test_apple_metrics_worker.py,tests/test_apple_metrics_schedule_selection.py,tests/test_apple_metrics_schedule.py,tests/test_apple_metrics_surface.py | verify=`python -m unittest tests.test_apple_metrics_worker tests.test_apple_metrics_schedule_selection tests.test_apple_metrics_schedule tests.test_apple_metrics_surface -v` | Verify exact and scheduled reads, schedule recovery, export safety and owner/agent surface readback.
- [ ] T12 | slice=plans | files=plans/apple-analytics-metrics.md | verify=`specline gate plan apple-analytics-metrics --approver codex-user-authorized --root .` | Keep provider and complete product acceptance distinct from synthetic tests.

The remaining T6-T10 paths are planned and must be checked against existing
worker, operation and UI interfaces before implementation; no assumed path or
interface above claims that unimplemented code exists.
Current provider data is private and may not yet include any report instance.
No actual metric, app outcome or provider/device acceptance is claimed.
The local transport packet passed 62 Apple analytics, parser, contract, store,
and segment-transport tests on Windows/Python 3.11.9. Apple's documented S3 sample
host pattern is the only accepted signed destination shape; provider endpoints,
credentials and live report instances remain unverified and are NOT_RUN.

T3 local verification covers the supported App Downloads Standard daily schema
and synthetic SQLite reconciliation only. The schema addition is forward-only
and idempotent through the existing `CREATE TABLE IF NOT EXISTS` initializer; it
does not backfill data. T5 now reads only an explicitly selected complete daily
`App Downloads Standard` instance. It rechecks current app and connection
authority under a SQLite write transaction, then persists observations and
completes the leased job in that same transaction. Its focused suite passed 6
tests and the combined Apple metrics, parser, transport, reconciliation and
worker suite passed 61 tests on Windows/Python 3.11.9. Tests use synthetic data;
no live Apple read, scheduled refresh, user-facing analytics view, additional
report family or account acceptance is claimed.
T4's exact transport and parser test command passed all 19 tests on Windows.
