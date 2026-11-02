# Plan: campaign-schedule-paid
Spec: specs/campaign-schedule-paid.md
Architect verdict: PASS

## Architecture
Each exact item identifies a fixed operation and immutable request. A retained worker capability binds the job and existing owner campaign authority. Existing intent and paid commitment admission remains authoritative. Legacy items omit operation and retain post semantics. Protective owner controls remain separate.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/campaign_schedule.py,mission_control/campaign_schedule_authority.py | verify=`python -m unittest tests.test_campaign_schedule -v` | Add paid review, typed capability and backward-compatible status.
- [ ] T2 | slice=mission_control | files=mission_control/worker.py | verify=`python -m unittest tests.test_campaign_schedule -v` | Preserve no-replay behavior for scheduled paid work.
- [ ] T3 | slice=tests | files=tests/test_campaign_schedule.py | verify=`python -m unittest tests.test_campaign_schedule -v` | Exercise paid admission, interruption, authority and old post batches with isolated fixtures.

## Gates
Run strict spec and validator gates before code; run focused tests, architecture and workflow evidence before completion. Live provider acceptance remains NOT_RUN.
