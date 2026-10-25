# Plan: agent-entrypoints
Spec: specs/agent-entrypoints.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/agent_setup.py | verify=`python -m unittest tests.test_agent_setup_entrypoint -q` | Implement offline setup_status, origin_guard and setup_privacy using existing origin validation.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/agent-control.js | verify=`node --test tests/agent_control.test.cjs` | Implement setup_frontdoor using native disclosure and existing permission controls.
- [ ] T3 | slice=docs | files=docs/agent-quickstart.md,docs/agent-cli.md,docs/agent-mcp.md | verify=`python -m unittest tests.test_agent_setup_entrypoint -q` | Document exact launch paths and current catalog authority without fixed tool counts.
- [ ] T4 | slice=tests | files=tests/test_agent_setup_entrypoint.py,tests/agent_control.test.cjs | verify=`python -m unittest tests.test_agent_setup_entrypoint -q` | Prove missing dependencies, origins, credential exclusion and launch configuration discovery from another directory.
- [ ] T5 | slice=README.md | files=README.md | verify=`python -m mission_control.agent_setup --help` | Put CLI and MCP setup in the repository front door.

## Gates
Strict specification, validator mutations, atomic tasks, focused tests, actual
offline CLI/MCP entrypoint launch checks and hash-bound workflow audit. Host
registration, live grant issuance and provider connection are not performed.
