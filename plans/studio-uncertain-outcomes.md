# Plan: studio-uncertain-outcomes
Spec: specs/studio-uncertain-outcomes.md
Architect verdict: PASS

## Architecture
Introduce an explicit fixed-message uncertain-effect exception, distinct from a
known input rejection. Broker dispatch raises it after durable intent if response,
source verification, finalization or result readback cannot confirm the result.
Keep retained ledger outcomes intact. Reviewed dispatch and standing execution
classify this type before validation and cancellation. No dictionary heuristics,
generic exception text or caller flags establish effect certainty.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/operation_outcome.py,mission_control/hypit_parameter_broker.py | verify=`python -m unittest tests.test_hypit_parameter_broker -v` | Implement studio_uncertain and uncertain_privacy with unchanged one-send and ledger rules.
- [ ] T2 | slice=mission_control | files=mission_control/agent_review_dispatch.py,mission_control/automation_execution.py | verify=`python -m unittest tests.test_agent_review_dispatch tests.test_automation_execution -v` | Implement review_uncertain and standing_uncertain before existing known_outcomes classification.
- [ ] T3 | slice=tests | files=tests/test_hypit_parameter_broker.py,tests/test_agent_review_dispatch.py,tests/test_automation_execution.py | verify=`python -m unittest tests.test_hypit_parameter_broker tests.test_agent_review_dispatch tests.test_automation_execution -v` | Prove uncertainty without local commits, cancellation, postcommit readback loss, privacy and no replay.

## Gates
CF doctor, strict/validator/task gates, actual controlled HTTP and SQLite dispatch
tests, deliberate classification mutations, independent Astra review, distribution
privacy and hash-bound workflow audit. Retained uncertain retry results remain
inspectable internally; a future public broker service must explicitly project
their uncertainty. Public admission/identity context and complete editing remain
required parent work. No deployment, spending or publication is authorized.
