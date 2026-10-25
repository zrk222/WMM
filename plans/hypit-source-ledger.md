# Plan: hypit-source-ledger
Spec: specs/hypit-source-ledger.md
Architect verdict: PASS

## Architecture
Three additive tables retain source versions, current heads and edit attempts.
Every mutation uses the existing guarded SQLite transaction. An internal trusted
broker supplies current admitted identity/context and authentic upstream source
observations; the ledger alone does not approve them. Immutable source content and
intent hashes bind retries, result transitions and private-source retention.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/db.py,mission_control/hypit_source_ledger.py | verify=`python -m unittest tests.test_hypit_source_ledger -v` | Implement source_versions, edit_intent, uncertain_recovery, edit_result, source_integrity and ledger_receipts.
- [ ] T2 | slice=tests | files=tests/test_hypit_source_ledger.py | verify=`python -m unittest tests.test_hypit_source_ledger -v` | Prove restart/concurrency, app isolation, exact retry binding, atomic result/head updates, rejected source preservation and private receipt boundaries.

## Gates
Scoped CF strict/requirement mutation/tasks, database and ledger tests, source
mutations, privacy and hash-bound workflow QA. Live broker edits, independent
checkpoints, UI/CLI/MCP and media rendering remain required parent work.
