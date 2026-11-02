# Plan: campaign-execution
Spec: specs/campaign-execution.md
Architect verdict: PASS

## Architecture
Owner scope and execution intents use SQLite atomic admission. Fixed Meta transport uses protected credentials and revalidates current authority before each network request. Unknown mutations remain held and cannot be replayed. Provider media budget and account semantics require verified readback; live acceptance remains NOT_RUN.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/campaign_contract.py,mission_control/campaign_transport.py | verify=`python -m unittest tests.test_campaign_execution -v` | Define finite input contracts and fixed provider routes with bounded transport.
- [ ] T2 | slice=mission_control | files=mission_control/campaign_execution.py | verify=`python -m unittest tests.test_campaign_execution -v` | Implement owner scope, durable intents, reservations, verification and protective stop.
- [ ] T3 | slice=tests | files=tests/test_campaign_execution.py | verify=`python -m unittest tests.test_campaign_execution -v` | Exercise admission, uncertainty, concurrency, budget and secret boundaries with synthetic fixtures.

## Gates
Run CF doctor, strict spec and validator gate before source changes. Run focused tests, architecture review, regression and workflow evidence gate before claiming completion. Live provider acceptance is NOT_RUN.
