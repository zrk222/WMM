# Plan: campaign-schedule
Spec: specs/campaign-schedule.md
Architect verdict: PASS

## Architecture
Persist one-shot owner-reviewed posts under a separate retained capability. The existing campaign engine remains the effect authority. Worker expiry blocks replay and OFF blocks future admissions. Network calls never hold a database writer transaction.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/campaign_schedule.py,mission_control/campaign_schedule_authority.py | verify=`python -m unittest tests.test_campaign_schedule -v` | Implement finite batch review, retained authority and atomic due admission.
- [ ] T2 | slice=mission_control | files=mission_control/campaign_access.py,mission_control/worker.py | verify=`python -m unittest tests.test_campaign_schedule -v` | Integrate the constrained capability and no-replay worker handling.
- [ ] T3 | slice=tests | files=tests/test_campaign_schedule.py | verify=`python -m unittest tests.test_campaign_schedule -v` | Verify authority, idempotency, interruption and OFF with isolated fixtures.

## Gates
Run strict spec and validator gates before code; run focused tests, architecture and workflow evidence before completion. Live provider acceptance remains NOT_RUN.
