# Plan: agent-usage-kpi
Spec: specs/agent-usage-kpi.md
Architect verdict: PASS

## Architecture
Add a finite usage normalizer to the existing selected-connection completion path.
Canonical reported fields and known protocol aliases map to input/output/total;
known cache and reasoning subsets remain separate observations. Invalid aliases
or conflicting counts invalidate only their affected field, with closed diagnostics.
No computed total, automatic price, credential, provider retry or raw usage object
is persisted. Successful draft output remains independent of absent/invalid telemetry.
Existing durable jobs provide restart/replay storage.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/agent_usage.py,mission_control/agent_tasks.py | verify=`python -m unittest tests.test_agent_usage -v` | Implement usage_mapping, usage_validation, usage_details, usage_uncertainty and usage_privacy in the shared successful result path.
- [x] T2 | slice=tests | files=tests/test_agent_usage.py | verify=`python -m unittest tests.test_agent_usage tests.test_agent_tasks tests.test_agent_native tests.test_local_agent_api -v` | Prove usage_persistence through isolated workers with canonical/compatible/native usage, invalid aliases, zero/missing telemetry, restart and idempotent replay.

## Gates
Strict spec and requirement mutation checks precede implementation. Require scoped
CF architecture, QA, behavioral negative/source mutation proof, privacy and exact
hash-bound workflow evidence. The wider regression is required after runtime edits;
no dashboard, complete KPI coverage, Hypit integration or whole-product readiness
claim follows from this packet alone.
