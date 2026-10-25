# Plan: personal-agent-operations
Spec: specs/personal-agent-operations.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/personal_agent_profiles.py,mission_control/agent_operations.py | verify=`python -m unittest tests.test_personal_agent_profiles -q` | Emit profile_contract, guide_scope, guide_authority and guide_discovery through existing discovery.
- [ ] T2 | slice=tests | files=tests/test_personal_agent_profiles.py | verify=`python -m unittest tests.test_personal_agent_profiles -q` | Prove profile classifications, scope changes and actual HTTP CLI MCP discovery.
- [ ] T3 | slice=docs | files=docs/personal-agent-operations.md | verify=`python -m unittest tests.test_personal_agent_profiles -q` | Document host-specific instructions, connection limits and receipt format.

## Gates
SpecLine strict and validator checks, focused runtime checks and hash-bound CF workflow audit. Live personal-provider acceptance remains separate.
