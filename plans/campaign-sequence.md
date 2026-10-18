# Plan: campaign-sequence
Spec: specs/campaign-sequence.md
Architect verdict: PASS

## Logical decomposition (phases)
1. Derive and freeze a finite sequence from existing source-bound resolution options.
2. Persist approval, child ownership, checkpoints and cancellation.
3. Advance through the durable worker and propagate ownership into source enqueue.
4. Expose strict APIs, typed feedback and a readable review/progress UI.
5. Verify restart, negative authority, cancellation races and desktop/mobile journeys.

## Tasks (atomic — each independently shippable)
- [x] T1 | slice=mission_control | files=mission_control/sequence_plan.py,mission_control/marketing_agent_manifest.py,tests/test_sequence_plan.py | verify=`python -m unittest tests.test_sequence_plan -q` | Derive and freeze the reviewed finite action list.
- [x] T2 | slice=mission_control | files=mission_control/sequence_store.py,mission_control/sequence_jobs.py,mission_control/db.py,tests/test_sequences.py | verify=`python -m unittest tests.test_sequences -q` | Persist exact approvals, owned/shared child references and cancellation.
- [x] T3 | slice=mission_control | files=mission_control/sequence_runtime.py,mission_control/worker.py,tests/test_sequence_runtime.py | verify=`python -m unittest tests.test_sequence_runtime -q` | Advance saved checkpoints through the worker and reject stale owned execution.
- [x] T4 | slice=mission_control | files=mission_control/campaign_inputs.py,mission_control/resolution_tools.py,tests/test_sequence_runtime.py | verify=`python -m unittest tests.test_sequence_runtime tests.test_source_retry -q` | Link source reads atomically to approved sequence ownership without changing shared reads.
- [x] T5 | slice=mission_control | files=mission_control/service.py,mission_control/server.py,mission_control/agent_feedback.py,tests/test_sequence_http.py | verify=`python -m unittest tests.test_sequence_http tests.test_agent_feedback -q` | Wire app-scoped APIs and sanitized progress into existing feedback.
- [x] T6 | slice=mission_control/static | files=mission_control/static/campaign-sequence.js,mission_control/static/index.html,mission_control/static/automatic-preparation.js | verify=`node --check mission_control/static/campaign-sequence.js` | Add readable review, selection, progress and cancellation controls.
- [x] T7 | slice=tools | files=tools/test_sequence_browser.py | verify=`python tools/test_sequence_browser.py` | Prove actual desktop/mobile review, approval, progress and cancellation behavior.
- [x] T8 | slice=smoke | files=smoke/campaign-sequence.json | verify=`forge smoke campaign-sequence --root .` | Prove non-hollow runtime behavior before scoped release.
- [x] T9 | slice=README.md | files=README.md | verify=`python tools/check_distribution.py` | Explain approval, progress, cancellation and remaining campaign limits without private app details.
