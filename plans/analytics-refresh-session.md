# Plan: analytics-refresh-session
Spec: specs/analytics-refresh-session.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/db.py,mission_control/insights.py | verify=`python -m unittest tests.test_analytics_refresh_session tests.test_measurement_connectors -v` | Reuse one connection while preserving guarded independently committed phases and transaction-free provider I/O.
- [ ] T2 | slice=tests | files=tests/test_analytics_refresh_session.py | verify=`python -m unittest tests.test_analytics_refresh_session -v` | Verify committed lease, unlocked external interval, authority checks, connection closure and retained failure evidence.
- [ ] T3 | slice=smoke | files=smoke/analytics-refresh-session.json | verify=`forge smoke analytics-refresh-session --root .` | Require actual transaction and performance acceptance without changing existing limits.
