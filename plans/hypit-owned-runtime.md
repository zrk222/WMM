# Plan: hypit-owned-runtime
Spec: specs/hypit-owned-runtime.md
Architect verdict: PASS

## Architecture
Use agent_process.capture with fixed argv and a private declarative project. Detect
and hash the local launcher. Staging uses exclusive creation and a caller-owned
empty folder; no external source or component code is accepted. Compiler/plan must
select only the fixed local rendering/media endpoints. Submit once, retain the ID,
observe that ID to terminal, export and decode. Always stop the private runtime;
on failure also cancel the known build before shutdown. Preserve project history.
Record cleanup failures distinctly and never infer success from a submission.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_runtime.py | verify=`python -m unittest tests.test_hypit_runtime -v` | Implement runtime_identity, private_project, local_graph, actual_build, owned_execution and runtime_cleanup with existing bounded process runner and dedicated media validator.
- [ ] T2 | slice=tests | files=tests/test_hypit_runtime.py | verify=`python -m unittest tests.test_hypit_runtime -v` | Prove local endpoint admission, single submission, matching identity, exact commands, cancellation/timeout cleanup and safe errors; retain a separate real installed build/export/decode run.

## Gates
CF strict and requirement mutations before coding; actual runtime, source mutants,
architecture, lint, privacy and workflow QA before completion. Durable job and
UI/CLI/MCP integration remain required after this runtime packet.
