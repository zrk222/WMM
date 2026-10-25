# Plan: hypit-studio-process
Spec: specs/hypit-studio-process.md
Architect verdict: PASS

## Architecture
The process adapter consumes an internally approved project and exact installation
fingerprint. Separate project validation from child lifecycle. Fixed local-only
preflight, private retained state, fixed GET observations and actual cleanup have
no public operation registration yet. The parent broker must enforce app/rights/
grant/standing approval and normalize compiled identities before exposing controls.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_studio_project.py | verify=`python -m unittest tests.test_hypit_studio_process -v` | Implement studio_preflight and exact source validation for studio_read and safe studio_close.
- [ ] T2 | slice=mission_control | files=mission_control/hypit_studio_process.py | verify=`python -m unittest tests.test_hypit_studio_process -v` | Implement studio_owned_start, studio_read, studio_close and studio_recovery over live owned child handles.
- [ ] T3 | slice=tests | files=tests/test_hypit_studio_process.py | verify=`python -m unittest tests.test_hypit_studio_process -v` | Prove validation, retained attempt denial, caller cancellation, source/HTTP/log boundaries and private cleanup; retain real installed Studio read/stop evidence.
- [ ] T4 | slice=mission_control | files=mission_control/hypit_studio_http.py,mission_control/agent_process.py | verify=`python -m unittest tests.test_hypit_studio_process tests.test_agent_native -v` | Repair studio_read with total transport deadlines and studio_recovery with bounded private capture diagnostics before deletion.
- [ ] T5 | slice=tests | files=tests/test_agent_native.py | verify=`python -m unittest tests.test_agent_native -v` | Prove studio_recovery diagnostics survive real native nonzero exit, timeout and process creation failure without altering default capture behavior.
- [ ] T6 | slice=mission_control | files=mission_control/studio_child.py | verify=`python -m unittest tests.test_studio_child -v` | Implement studio_close and studio_recovery using retained Windows Job Object authority, continuously capped output and verified listener ownership for studio_read.
- [ ] T7 | slice=tests | files=tests/test_studio_child.py | verify=`python -m unittest tests.test_studio_child -v` | Prove real descendant termination after launcher exit, independent output bounds and owned versus foreign listener admission through studio_close and studio_read.
- [ ] T8 | slice=mission_control | files=mission_control/studio_command.py | verify=`python -m unittest tests.test_studio_command tests.test_hypit_studio_process -v` | Implement studio_recovery and studio_close for synchronous command Job ownership and pending native-launch rollback handles.
- [ ] T9 | slice=tests | files=tests/test_studio_command.py | verify=`python -m unittest tests.test_studio_command -v` | Prove studio_recovery retains diagnostics and requires command-tree cleanup including launch failures, cancellation and exited-launcher descendants.

## Gates
CF strict/mutations/tasks, scoped Forge architecture/nonhollow smoke, focused
regression and source mutations, actual installed startup/snapshot/cleanup and
hash-bound workflow QA. No public UI/MCP/approval or final-media claim for this
internal adapter. Do not declare the full Studio feature complete here.
