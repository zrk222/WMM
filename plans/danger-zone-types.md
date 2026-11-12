# Plan: danger-zone-types
Spec: specs/danger-zone-types.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/common.py,mission_control/operation_catalog.py,mission_control/campaign_contract.py | verify=`python tools/check_types.py` | Type validators and exact normalized request shapes without changing errors.
- [ ] T2 | slice=mission_control | files=mission_control/agent_grants.py,mission_control/review_access.py | verify=`python -m unittest tests.test_agent_grants tests.test_verified_review -q` | Apply generated full-row types at grant and role boundaries.
- [ ] T3 | slice=tools | files=tools/check_types.py,tools/maintained_files.txt,tools/maintained_js.txt,tools/danger_zone_types.py | verify=`python tools/check_types.py` | Run standard analysis only on the maintained list and fail named boundary annotation regression.
- [ ] T4 | slice=pyrightconfig.json | files=pyrightconfig.json | verify=`python tools/check_types.py` | Raise maintained type checking to standard without broad legacy enrollment.
- [ ] T5 | slice=tests | files=tests/test_danger_zone_types.py | verify=`python -m unittest tests.test_danger_zone_types -q` | Prove missing annotations and invalid generated-row assignments are rejected.
- [ ] T6 | slice=docs | files=docs/MAINTAINABILITY.md | verify=`python tools/check_types.py` | Record exact typed scope and static/runtime evidence boundaries.
