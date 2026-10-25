# Plan: managed-media-validation
Spec: specs/managed-media-validation.md
Architect verdict: PASS (existing authorized UGC/stitching scope; local CLI review)

## Architecture
One private bytes-to-metadata boundary stages only generated names and invokes
existing bounded native capture. Separate metadata normalization from probe/decode
execution so numeric, stream and ambiguity checks are independently testable.
The original input hash and actual decoded-frame evidence are outputs; reuse
rights and app-source binding belong to subsequent app-owned intake integration.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/managed_media_validation.py | verify=`python -m unittest tests.test_managed_media_validation -q` | Implement media_bytes, media_metadata and media_decode without user filter or path execution.
- [x] T2 | slice=tests | files=tests/test_managed_media_validation.py | verify=`python -m unittest tests.test_managed_media_validation tests.test_hypit_media -q` | Cover finite bounds, ambiguous streams, actual MP4/MOV/WebM audio, the maximum-duration/sample-rate boundary, silent input and failing decode with synthetic data.
- [x] T3 | slice=specs | files=specs/managed-media-validation.md,specs/managed-media-validation.ssat.yaml | verify=`specline strict managed-media-validation --root .; forge verify-tests managed-media-validation specs/managed-media-validation.ssat.yaml --root .` | Bind source and tests to the three written boundary requirements.
- [x] T4 | slice=smoke | files=smoke/managed-media-validation.json | verify=`forge verify-tests managed-media-validation specs/managed-media-validation.ssat.yaml --root .; forge smoke managed-media-validation --root .` | Run the real validator over generated local video-plus-audio bytes and verify digest, audio presence and decoded frame evidence.
- [x] T5 | slice=.factory/managed-media-validation | files=.factory/managed-media-validation/contract.json,.factory/managed-media-validation/observations.json | verify=`factory audit workflows --root . --contract .factory/managed-media-validation/contract.json --observations .factory/managed-media-validation/observations.json --json` | Bind source, tests, requirements and actual/mutant evidence; retain all failures and parent integration gaps.

## Gates
CF doctor; strict spec and deleted-requirement validators; atomic tasks; scoped
Forge architecture/QA/review; non-hollow smoke; boundary source mutants; actual
local video-plus-audio decode; privacy and project-neutral workflow audit. No
complete UGC/stitching or release claim from this implementation packet.
