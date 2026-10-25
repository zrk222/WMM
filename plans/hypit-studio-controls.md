# Plan: hypit-studio-controls
Spec: specs/hypit-studio-controls.md
Architect verdict: PASS

## Architecture
One WMM-owned broker manages a selected Hypit Studio process and project closure.
It admits typed app-scoped operations and validates current approval, runtime and
source identity before forwarding only adapter-owned requests. Compiled package
fields remain the authority for both UI controls and agent schemas. The broker
stores source versions, observed process/build identities and recoverable drafts.
It never treats loopback, upstream same-origin admission or preview success as
WMM authorization. No unsupervised direct Studio iframe can bypass the broker's
mutation, runtime or credential boundaries.

The source review found a read-only durable runtime control alongside a distinct
transient execution host. Both paths need explicit execution admission. Connecting
only the durable build checks would leave preview outside the approved profile.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_studio_sessions.py,mission_control/hypit_studio_process.py | verify=`python -m unittest tests.test_hypit_studio_sessions -v` | Implement owned_session, execution_authority and session_recovery using exact owned project/process identities and bounded observations.
- [ ] T2 | slice=mission_control | files=mission_control/hypit_studio_documents.py,mission_control/hypit_studio_mutations.py | verify=`python -m unittest tests.test_hypit_studio_mutations -v` | Implement compiled_controls, parameter_transaction, semantic_timing and source_transaction using the actual upstream compiled schema and source history.
- [ ] T3 | slice=mission_control | files=mission_control/hypit_studio_library.py,mission_control/hypit_studio_feedback.py | verify=`python -m unittest tests.test_hypit_studio_library -v` | Implement results_library, accepted_reuse and shared_feedback with app/run identity and optimistic revisions.
- [ ] T4 | slice=mission_control | files=mission_control/hypit_studio_exports.py,mission_control/hypit_studio_reporting.py | verify=`python -m unittest tests.test_hypit_studio_exports -v` | Implement portable_project and live_reporting with measured observations and clean offline restoration.
- [ ] T5 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py,mission_control/automation_requirements.py,mission_control/server.py | verify=`python -m unittest tests.test_hypit_studio_clients -v` | Connect operation_parity through existing owner/grant/review admission; keep every operation subject to fresh execution_authority.
- [ ] T6 | slice=mission_control/static | files=mission_control/static/hypit-studio.js,mission_control/static/hypit-studio.css,mission_control/static/app.js,mission_control/static/ui-stories.js | verify=`node --test tests/hypit_studio.test.cjs` | Deliver complete human compiled_controls, media_preview, shared_feedback, live_reporting and recovery with Nanna guidance.
- [ ] T7 | slice=tests | files=tests/test_hypit_studio_sessions.py,tests/test_hypit_studio_mutations.py,tests/test_hypit_studio_library.py,tests/test_hypit_studio_exports.py | verify=`python -m unittest tests.test_hypit_studio_sessions tests.test_hypit_studio_mutations tests.test_hypit_studio_library tests.test_hypit_studio_exports -v` | Prove typed transactions, execution_authority, recovery and portable_project against actual installed local Hypit as well as controlled negative fixtures.
- [ ] T8 | slice=tests | files=tests/test_hypit_studio_clients.py,tests/hypit_studio.test.cjs | verify=`python -m unittest tests.test_hypit_studio_clients -v` | Prove operation_parity using real HTTP/CLI/MCP clients plus desktop/mobile media_preview, conflicts, keyboard operation, cancellation and PDF readback.

## Gates
Before implementation, verify installed Hypit versions and package/runtime hashes
against the source ABI; do not assume the inspected upstream clone equals the
installed distribution. Freeze adapter limits and typed operation schemas in the
implementation packet. Run strict requirement mutation, atomic task validation,
appropriate Forge architecture/test/smoke and Prestige checks, source mutations,
privacy checks and hash-bound workflow QA. Retain first failures. No task above
is implemented or tested merely because this plan passes a planning validator.

## Delivery order
Complete the owned broker and its local-only transient preview admission first;
then compiled read/mutate, source history, library/feedback, clients and full human
controls. Verify a complete actual-media workflow before committing its milestone.
Keep full OpenCut controls, selected-agent authoring and the complete marketer
matrix required. No narrower editor profile substitutes for the user's goal.
