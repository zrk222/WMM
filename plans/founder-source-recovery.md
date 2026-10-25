# Plan: founder-source-recovery
Spec: specs/founder-source-recovery.md
Architect verdict: PASS

## Architecture
Extend unified review issue projection with validated customer readout states and
saved ads-source states. Detailed services remain authoritative. Use fixed repair
guidance; no raw excerpts or diagnostic strings enter the issue summary.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/subscription_review.py | verify=`python -m unittest tests.test_subscription_review -v` | Implement customer_recovery, account_recovery, scoped_recovery and review_state using existing scoped records.
- [ ] T2 | slice=tests | files=tests/test_subscription_review.py | verify=`python -m unittest tests.test_subscription_review -v` | Prove expiry, removed evidence, changed app scope, invalid account binding, positive current sources and privacy through service and HTTP paths.

## Gates
Strict requirements and validator mutations; focused service/HTTP regression;
source mutation challenge; unchanged applicable browser/report flows; distribution
privacy and hash-bound workflow audit. Preserve unrelated work and Hypit ledger.
