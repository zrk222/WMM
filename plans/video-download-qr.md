# Plan: video-download-qr
Spec: specs/video-download-qr.md
Architect verdict: PASS

## Logical decomposition
1. Bind the app's store identity and render the QR before artifact hashing.
2. Bind the reviewed QR choice to new video effects and preserve historical reads.
3. Verify final pixels, owner preview, and the pinned dependency.

## Tasks (atomic)
- [ ] T1 | slice=mission_control | files=mission_control/video_download_qr.py,mission_control/hypit_runtime.py,mission_control/hypit_authoring.py,mission_control/hypit_jobs.py | verify=`python -m unittest tests.test_video_download_qr` | Stamp validated final Hypit bytes using the saved app's direct store URL.
- [ ] T2 | slice=mission_control | files=mission_control/publication_artifacts.py,mission_control/campaign_video_execution.py,mission_control/organic_video_policy.py | verify=`python -m unittest tests.test_publication_authority tests.test_organic_video_policy` | Require a retained QR receipt or explicit opt-out before new publication; preserve reconciliation.
- [ ] T3 | slice=mission_control/static | files=mission_control/static/creative-rendering.mjs,mission_control/static/organic-research.js | verify=`node --test tests/hypit-interface.test.mjs` | Expose QR choice in Studio and organic video production, and show the choice in review.
- [ ] T4 | slice=tests | files=tests/test_video_download_qr.py | verify=`python -m unittest tests.test_video_download_qr` | Decode final pixels and exercise provenance denial.
