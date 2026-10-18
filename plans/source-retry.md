# Plan: source-retry
Spec: specs/source-retry.md
Architect verdict: PASS

## Logical decomposition (phases)
1. Add bounded app-scoped retry projection and atomic enqueue.
2. Connect retry proposals to existing approval, execution and feedback.
3. Verify end-to-end restart, replay, denial, source changes and actual result dialogs.

## Tasks (atomic — each independently shippable)
- [x] T1 | slice=mission_control | files=mission_control/source_retry.py,mission_control/campaign_inputs.py | verify=`python -m unittest tests.test_source_retry -q` | Add exact retry projection and atomic source-read enqueue without network access.
- [x] T2 | slice=mission_control | files=mission_control/resolution_plan.py,mission_control/resolution_tools.py,mission_control/resolution_catalog.py,mission_control/marketing_agent_manifest.py | verify=`python -m unittest tests.test_source_retry tests.test_resolutions -q` | Wire explained retry choices into existing approval and worker readback.
- [x] T3 | slice=tests | files=tests/test_source_retry.py,tests/test_source_retry_guards.py | verify=`python -m unittest discover -s tests -p test_*.py` | Prove recovery, replay, source binding, bounds and preservation of original receipts.
