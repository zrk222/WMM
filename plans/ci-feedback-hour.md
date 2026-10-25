# Plan: ci-feedback-hour
Spec: specs/ci-feedback-hour.md
Architect verdict: PASS

- [x] T1 | slice=tests | files=tests/test_agent_feedback.py | verify=`python -m unittest tests.test_agent_feedback -v` | Pin the collection fixture clock and verify stale hourly approval rejection plus refreshed approval.
- [x] T2 | slice=.factory/ci-feedback-hour | files=.factory/ci-feedback-hour/contract.json,.factory/ci-feedback-hour/observations.json | verify=`factory audit workflows --root . --contract .factory/ci-feedback-hour/contract.json --observations .factory/ci-feedback-hour/observations.json --json` | Retain failed hosted evidence and bind scoped proof to candidate hashes.
