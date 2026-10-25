# Plan: native-timeout-diagnostics
Spec: specs/native-timeout-diagnostics.md
Architect verdict: PASS

## Architecture
Use a test-local wrapper around the real process wait. Observe flushed stdout
and stderr before starting its unchanged timeout. Bound readiness separately and
keep failure cleanup owned by capture. Deliberately delay the child startup to
reproduce the old test's scheduling assumption. Do not change runtime code.

## Tasks
- [ ] T1 | slice=tests | files=tests/test_agent_native.py | verify=`python -m unittest tests.test_agent_native -v` | Prove diagnostic_readiness, diagnostic_retention and diagnostic_creation with a real child and unchanged runtime.

## Gates
CF strict, validator mutations and tasks; repeated actual-child test; a removed
readiness-wrapper mutation and missing-output mutation must fail; privacy and
hash-bound workflow audit. Preserve the previous full-suite failure evidence.
Run the complete regression before claiming the whole checkout passes.
