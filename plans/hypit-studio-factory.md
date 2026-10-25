# Plan: hypit-studio-factory
Spec: specs/hypit-studio-factory.md
Architect verdict: PASS

## Architecture
Resolve a source job by exact app/job identity from SQLite and use current_inputs
to validate frozen brief/rights. Build deterministic fixed authoring files in
memory, fingerprint the installed Hypit distribution, read a host-selected font
with stable inode/size/hash and freeze the complete public execution summary.
Creation rechecks this summary against the exact PREPARED registry intent, then
creates only the internal session UUID under a fixed app-hashed private root.
Validate every existing path component, reject links/reparse points and use
exclusive creation. Copy exact generated UTF8 bytes and frozen font bytes without
using the render job folder or inherited runtime. Recheck source and installation
after writes, then return a NEW StudioProcess and internal source manifest. No
process or external endpoint is started here; caller controls admission/lifecycle.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_studio_factory.py | verify=`python -m unittest tests.test_hypit_studio_factory -v` | Implement factory_plan, factory_source, factory_reservation, factory_isolation, factory_paths and factory_ready.
- [ ] T2 | slice=tests | files=tests/test_hypit_studio_factory.py | verify=`python -m unittest tests.test_hypit_studio_factory -v` | Prove actual SQLite source/registry checks, exact isolated files, privacy, source/font/install drift and no child launch.

## Gates
CF strict/validator/task gates, focused behavioral tests and guard mutations,
independent Astra static review, actual installed synthetic factory+Studio probe,
privacy checks and hash-bound workflow audit. Complete session manager, authority
callbacks, public clients, restart reconciliation and full editor remain required.
