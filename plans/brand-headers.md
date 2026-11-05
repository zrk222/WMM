# Plan: brand-headers
Spec: specs/brand-headers.md
Architect verdict: PASS for presentation-only work in existing web, documentation and native workspace surfaces.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/static/index.html,mission_control/static/style.css | verify=`python tools/test_agent_task_presets_browser.py` | Move the existing web brand into a visible product header, preserve context and make mobile navigation use the available width.
- [ ] T2 | slice=docs | files=docs/index.html,docs/demo.html | verify=`prestige audit docs/index.html --strict` | Apply the same mark and full name in both public headers, retaining navigation and demo actions.
- [ ] T3 | slice=ios | files=ios/WMM/Workflow/WorkflowNavigation.swift | verify=`python tools/check_platform_receipts.py --ci-contract` | Apply the same identity in the independent native workspace, preserving its selected app context and controls; require both simulator lanes before merge.
- [ ] T4 | slice=docs | files=docs/images/sample-workflow.png,docs/images/provenance.json | verify=`python tools/check_distribution.py` | Refresh the existing README sample image from the actual branded synthetic browser journey and update its exact capture hash using the existing provenance gate.

## Evidence
Run actual desktop and narrow browser renders, the sample journey, distribution, SpecLine and hash-bound workflow checks. Use the PR's current Windows, Ubuntu, browser and native checks for final integration.
