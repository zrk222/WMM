# Plan: campaign-paid-schedule-ui
Spec: specs/campaign-paid-schedule-ui.md
Architect verdict: PASS

## Architecture
The UI presents exact approved scope and verified-post identities, prepares a single bounded paid request and displays the server summary for owner activation. Existing server authorization remains authoritative. Saved progress distinguishes provider receipt and commitment from app outcomes.

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/campaign-execution.js | verify=`node --test tests/campaign_schedule_ui.test.cjs` | Add exact paid schedule review and saved receipt reporting.
- [ ] T2 | slice=tests | files=tests/campaign_schedule_ui.test.cjs | verify=`node --test tests/campaign_schedule_ui.test.cjs` | Exercise validation, stale guards, duplicate submissions and report privacy with synthetic data.

- [ ] T3 | slice=tests | files=tests/campaign_paid_schedule_browser.py | verify=`python tests/campaign_paid_schedule_browser.py` | Exercise exact review, focus, activation and sanitized progress at desktop/mobile widths with all live network blocked.

## Gates
Run strict and validator gates before code. Run focused synthetic tests, applicable design checks and hash-bound workflow audit before completion. Live Meta acceptance remains NOT_RUN.
