# Plan: source-first-app-setup
Spec: specs/source-first-app-setup.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/static/app-ui.mjs,mission_control/static/app-events.mjs | verify=`node --test tests/owner_onboarding.test.cjs` | Open existing public-source review from an explicit local first-run draft.
- [ ] T2 | slice=mission_control | files=mission_control/setup_parse.py | verify=`python -m unittest tests.test_setup_discovery` | Bind directly inspected Apple listing identities to the source field proposal.
- [ ] T3 | slice=tests | files=tests/test_source_first_setup.py | verify=`python -m unittest tests.test_source_first_setup` | Verify link and manual paths with keyboard, no external reads on save and no cross-app navigation.
- [ ] T4 | slice=mission_control | files=mission_control/store.py,mission_control/setup_discovery.py,mission_control/static/setup-discovery.mjs | verify=`python -m unittest tests.test_source_first_setup tests.test_setup_discovery` | Keep the lookup source separate from the campaign tracking website; existing website-only apps still work.
