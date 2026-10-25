# Plan: hypit-media-profile
Spec: specs/hypit-media-profile.md
Architect verdict: PASS

## Architecture
Reuse agent_process.capture for owned local FFprobe execution with restricted
environment, output bounds and cleanup. Probe a caller-owned bounded artifact, normalize exactly one
video and optional AAC stream, validate expected shape/time and return exact byte
hashes. Import shared dimensions but do not alter media_native.py. Validate numeric
metadata and malformed decoder errors without exposing raw diagnostic bodies.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/hypit_media.py | verify=`python -m unittest tests.test_hypit_media -v` | Implement video_profile, audio_profile, artifact_validation, separate_profiles and decoder_boundary in a dedicated validator.
- [x] T2 | slice=tests | files=tests/test_hypit_media.py | verify=`python -m unittest tests.test_hypit_media tests.test_creative_rendering -q` | Decode actual temporary synthetic H.264/AAC media and exercise unsupported streams, malformed/timing/shape inputs, deadline and native-profile separation.

## Gates
Run strict specification and requirement mutation checks before implementation.
Require actual decode, meaningful source mutants, scoped CF QA/architecture, privacy
and hash-bound workflow QA before claiming this packet complete. Full Hypit jobs,
UI, editing, agent authoring and complete KPI scope remain required elsewhere.
