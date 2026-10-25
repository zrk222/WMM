# Plan: analytics-read-indexes
Spec: specs/analytics-read-indexes.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/db.py,mission_control/insights.py | verify=`python -m unittest tests.test_analytics_read_indexes tests.test_measurement_connectors -v` | Index current scoped read queries and count rolling quotas only where the provider enforces one.
- [ ] T2 | slice=tests | files=tests/test_analytics_read_indexes.py | verify=`python -m unittest tests.test_analytics_read_indexes -v` | Prove actual query-plan index use, preserved history and scoped quota behavior at scale.
- [ ] T3 | slice=smoke | files=smoke/analytics-read-indexes.json | verify=`forge smoke analytics-read-indexes --root .` | Require non-hollow real query-plan and unchanged workload checks before scoped delivery.
