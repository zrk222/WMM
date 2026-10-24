# Plan: hypit-declarative-authoring
Spec: specs/hypit-declarative-authoring.md
Architect verdict: PASS

## Architecture
Validate a closed JSON-like structure, escape literal text with the standard XML
encoder, and emit fixed built-in timeline, spatial, media-font, typography, film
and HTML-video surfaces. Only numeric validated duration/dimensions enter attributes;
scene text is XML content, never a reference or package name. A fixed local profile
selects HTML rasterization and local media muxing. The caller owns project creation,
font staging, actual source proof, agent approval, jobs and result lifecycle.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/hypit_authoring.py | verify=`python -m unittest tests.test_hypit_authoring -v` | Implement scene_contract, scene_validation, source_emission, project_boundary, authoring_receipt and code_boundary as a pure generator.
- [x] T2 | slice=tests | files=tests/test_hypit_authoring.py | verify=`python -m unittest tests.test_hypit_authoring -v` | Prove malformed/boundary cases, literal markup isolation, exact fixed files and deterministic receipts, then retain actual installed Hypit compiler and local rendering evidence separately.

## Gates
Require strict specification and requirement mutation gates before code; scoped CF
architecture, source mutations, privacy and hash-bound workflow QA before completion.
The actual installed runtime probe must use a marked isolated project with staged
local font; preserve compiler/build failures and do not mistake check or plan for
an MP4. Full WMM integration remains pending after this authoring packet.
