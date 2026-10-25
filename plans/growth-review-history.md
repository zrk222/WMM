# Plan: growth-review-history
Spec: specs/growth-review-history.md
Architect verdict: PASS

## Architecture
Reuse pure ASO/benchmark validators and existing app-owned jobs/records. Store immutable typed entries in an additive table, with public scope context and a hash over kind/data/context. Fresh readouts are derived and cannot authorize execution. Keep contracts separate from SQLite transactions. Imported entries retain assertion provenance and never restore credentials, grants or approvals.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/growth_review_contract.py,mission_control/growth_review_store.py,mission_control/db.py,tests/test_growth_review_store.py | verify=`python -m unittest tests.test_growth_review_store -v` | Implement immutable_history, scope_guard and fresh_readout for listings, references and exact-source editorial notes.
- [x] T2 | slice=mission_control | files=mission_control/benchmark_ads.py,mission_control/currency_units.py,tests/test_benchmark_ads.py | verify=`python -m unittest tests.test_benchmark_ads -v` | Implement ads_projection from current app-owned report jobs, sourced ISO minor-unit/date conversion and unavailable source handling.
- [x] T3 | slice=mission_control | files=mission_control/growth_review_contract.py,mission_control/growth_review_store.py,tests/test_growth_review_store.py | verify=`python -m unittest tests.test_growth_review_store tests.test_benchmark_ads -v` | Persist benchmark_comparison against an exact reference and saved report, retaining source lineage and stale-read recovery.
- [x] T4 | slice=mission_control | files=mission_control/growth_review_portable.py,mission_control/store.py,tests/test_growth_review_portable.py | verify=`python -m unittest tests.test_growth_review_portable -v` | Implement portable_history with atomic validation, legacy snapshot compatibility and imported-assertion provenance.
- [x] T5 | slice=mission_control | files=mission_control/subscription_review.py,mission_control/service.py,mission_control/server.py,tests/test_subscription_review.py | verify=`python -m unittest tests.test_subscription_review -v` | Implement review_api and unified evidence/recovery projection with exact HTTP shapes and existing CSRF boundaries.

## Acceptance and next integration
Regression repair scope: update `tests/test_outcome_learning.py` so its historical clock also governs the newly integrated subscription review. Verify `python -m unittest tests.test_http.HTTPTests.test_outcome_learning_fresh_identity_exact_approval_use_and_rollback -v`; retain the original failure and rerun the combined suite. This changes the synthetic clock, not production freshness checks.

Bind current candidate hashes, actual Python/SQLite/HTTP observations, negative cases and workflow audit before scoped completion. Source-only tests cannot establish real provider acceptance. Wire the resulting service into full UI, reports and agent interfaces; retain the all-features completion requirement. No release, spend or private activation is authorized.
