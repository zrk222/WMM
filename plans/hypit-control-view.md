# Plan: hypit-control-view
Spec: specs/hypit-control-view.md
Architect verdict: PASS

## Architecture
One pure projection module consumes an owned compiled snapshot and scope. It
keeps a private map of native parameter owners/fields and returns only explicit
public field metadata and opaque identities. Proposals resolve through that map,
bind the exact view hash/revision, and never execute or authorize a mutation.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_control_view.py | verify=`python -m unittest tests.test_hypit_control_view -v` | Implement control_inventory, control_privacy, control_binding, control_proposal and control_authority.
- [ ] T2 | slice=tests | files=tests/test_hypit_control_view.py | verify=`python -m unittest tests.test_hypit_control_view -v` | Prove all compiled owners/field shapes, opaque scope, stale/foreign denial, privacy, bounds and proposal-only authority.

## Gates
Scoped CF strict/requirement mutations/tasks, behavioral positive/negative tests,
source mutation checks and hash-bound workflow QA. Actual native mutation, broker
grants, UI/CLI/MCP and source history remain required parent work.
