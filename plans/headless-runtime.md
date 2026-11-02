# Plan: headless-runtime
Spec: specs/headless-runtime.md
Architect verdict: PASS

## Architecture
An OS-held workspace lock covers desktop and headless lifetime. The explicit headless entry reuses the existing server and workers with a fixed loopback port, same user database and shutdown cleanup.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/workspace_lock.py,mission_control/desktop.py | verify=`python -m unittest tests.test_workspace_lock tests.test_desktop_entry -v` | Implement workspace exclusion and explicit headless lifecycle.
- [ ] T2 | slice=tests | files=tests/test_workspace_lock.py,tests/test_desktop_entry.py | verify=`python -m unittest tests.test_workspace_lock tests.test_desktop_entry -v` | Exercise subprocess contention, failure, shutdown and private binding.

- [ ] T3 | slice=docs | files=docs/always-on-runtime.md | verify=`python -m unittest tests.test_desktop_entry tests.test_workspace_lock` | Document explicit owner-hosted process setup, same-user vault scope, private paths and shutdown limits.

## Gates
Run strict spec and validator gates before code. Run focused lifecycle tests, architecture review and hash-bound workflow audit before completion. Remote acceptance remains NOT_RUN.
