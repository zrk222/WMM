# Plan: sqlite-write-serialization
Spec: specs/sqlite-write-serialization.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/db.py | verify=`python -m unittest tests.test_sqlite_tuning -q` | Add explicit eager-lock write transactions, preserving legacy default read behavior and guard/rollback order.
- [ ] T2 | slice=tests | files=tests/test_sqlite_tuning.py | verify=`python -m unittest tests.test_sqlite_tuning tests.test_query_budgets -q` | Exercise two writers, readers, nested rejection, rollback and FULL durability.
- [ ] T3 | slice=docs | files=docs/MAINTAINABILITY.md | verify=`python -m unittest tests.test_sqlite_tuning -q` | Document explicit writer reservation, provider boundary and scope limits.
- [ ] T4 | slice=mission_control | files=mission_control/agent_tasks.py,mission_control/attribution_adservices.py,mission_control/attribution_ingestion.py,mission_control/audit_runtime.py | verify=`python -m unittest tests.test_sqlite_tuning tests.test_query_budgets -q` | Mark reviewed direct write scopes explicitly; preserve manual transaction boundaries.
- [ ] T5 | slice=mission_control | files=mission_control/cloud_connection.py,mission_control/connection_setup.py,mission_control/creative_rendering.py,mission_control/drive_import_jobs.py | verify=`python -m unittest tests.test_sqlite_tuning tests.test_query_budgets -q` | Mark reviewed direct write scopes explicitly; preserve manual transaction boundaries.
- [ ] T6 | slice=mission_control | files=mission_control/experiment_tracking.py,mission_control/hypit_jobs.py,mission_control/insights.py,mission_control/notices.py | verify=`python -m unittest tests.test_sqlite_tuning tests.test_query_budgets -q` | Mark reviewed direct write scopes explicitly; preserve manual transaction boundaries.
- [ ] T7 | slice=mission_control | files=mission_control/onesignal_setup.py,mission_control/payment_sources.py,mission_control/play_connections.py,mission_control/service.py | verify=`python -m unittest tests.test_sqlite_tuning tests.test_query_budgets -q` | Mark reviewed direct write scopes explicitly; preserve manual transaction boundaries.
- [ ] T8 | slice=mission_control | files=mission_control/social_renewal.py,mission_control/store.py,mission_control/storekit_ingestion.py | verify=`python -m unittest tests.test_sqlite_tuning tests.test_query_budgets -q` | Mark reviewed direct write scopes explicitly; preserve manual transaction boundaries.

- [ ] T9 | slice=smoke | files=smoke/sqlite-write-serialization.json | verify=`forge smoke sqlite-write-serialization` | Prove the scoped SQLite writer API and reject generated stubs; broader regression evidence remains separate.
