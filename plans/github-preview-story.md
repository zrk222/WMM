# Plan: github-preview-story
Spec: specs/github-preview-story.md
Architect verdict: PASS

## Architecture
Keep runtime and provider authority unchanged. Static README and visual tour use
the Nanna mission-to-evidence arc. A self-contained labelled synthetic HTML sample
provides a real interactive local-only consent/progress/report journey with no
network calls, external assets or credentials. Existing screenshots retain their
synthetic-data label. New screenshot is captured from the actual sample browser.

## Tasks
- [ ] T1 | slice=README.md | files=README.md | verify=`python tools/test_preview_browser.py` | Lead the GitHub overview with founder/team intent, human consent, agent work and concrete marketing deliverables; retain a current capability map and one primary action.
- [ ] T4 | slice=docs | files=docs/index.html,docs/.nojekyll | verify=`prestige audit docs/index.html` | Apply the story and design to the visual tour with one primary action; serve the static GitHub preview without a Jekyll transformation.
- [ ] T2 | slice=docs | files=docs/demo.html | verify=`python tools/test_preview_browser.py` | Implement goal/consent/progress/report, invalidated consent, export, keyboard and mobile behavior without external requests.
- [ ] T5 | slice=tools | files=tools/test_preview_browser.py | verify=`python tools/test_preview_browser.py` | Exercise actual desktop/mobile sample authority, exported receipts and no external calls.
- [ ] T3 | slice=docs | files=docs/images/sample-workflow.png | verify=`python tools/test_preview_browser.py` | Capture the actual sample UI for the GitHub README and visual tour; do not present it as live campaign evidence.

## Acceptance
Prestige audit, critique with strict challenge, render-audit and challenge on both
HTML surfaces; CF workflow QA binds source, acceptance and actual browser evidence.
Publication uses the owner's existing commit/push/merge authorization after checks.
