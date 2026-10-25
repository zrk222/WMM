# Plan: growth-funnels
Spec: specs/growth-funnels.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/funnel_contract.py,tests/test_funnel_contract.py | verify=`python -m unittest tests.test_funnel_contract -v` | Implement immutable outcome, creative, app-sales route and observation contracts with explicit comparability rules.
- [ ] T2 | slice=mission_control | files=mission_control/funnel_store.py,tests/test_funnel_store.py | verify=`python -m unittest tests.test_funnel_store -v` | Persist scoped definitions and observations, reconcile existing ledger references and prove restart, duplicates and stale context.
- [ ] T3 | slice=mission_control | files=mission_control/funnel_reporting.py,tests/test_funnel_reporting.py | verify=`python -m unittest tests.test_funnel_reporting -v` | Calculate qualified denominators, stage losses and currency-separated costs with unknown handling and no duplicate financial events.
- [ ] T4 | slice=mission_control | files=mission_control/funnel_http.py,tests/test_funnel_http.py | verify=`python -m unittest tests.test_funnel_http -v` | Expose shared owner/grant operations with exact framing, independent approval and uncertain-result reconciliation.
- [ ] T5 | slice=mission_control | files=mission_control/operation_catalog.py,tests/test_funnel_agent_transport.py | verify=`python -m unittest tests.test_funnel_agent_transport -v` | Prove real CLI and official MCP parity for every implemented funnel operation.
- [ ] T6 | slice=mission_control/static | files=mission_control/static/growth-funnels.js,tests/growth_funnels.test.cjs | verify=`node --test tests/growth_funnels.test.cjs` | Implement outcome brief, five app-sales phases, source/variant links, optional branches and live stage progress using Nanna and Prestige.
- [ ] T7 | slice=mission_control | files=mission_control/funnel_handoff.py,tests/test_funnel_handoff.py | verify=`python -m unittest tests.test_funnel_handoff -v` | Implement optional provider-supported resource/DM handoff with current eligibility and no unapproved send or spend.
- [ ] T8 | slice=mission_control | files=mission_control/subscription_review.py,tests/test_funnel_review.py | verify=`python -m unittest tests.test_funnel_review -v` | Integrate evidenced bottlenecks, next actions and source-bound PDF/structured reports into founder review.
- [ ] T9 | slice=.factory/growth-funnels | files=.factory/growth-funnels/contract.json,.factory/growth-funnels/observations.json | verify=`factory audit workflows --root . --contract .factory/growth-funnels/contract.json --observations .factory/growth-funnels/observations.json --json` | Bind source hashes, all applicable execution profiles, negative cases, privacy and retained failures; run clean CI before merge.

Implementation remains INCOMPLETE. Task paths describe intended scope and do not assert files or workflows already exist. Real provider effects, device acceptance and measured customer outcomes remain separate. Original UPG-00 through UPG-06 and all prior accepted additions remain active.

Architecture review: existing source owners and ledger reuse are identified in the specification. Two new immutable app-scoped resources hold only funnel definitions and upstream observations; no shadow payment ledger or parallel permissions. Unsupported external effects remain separate acceptance work. PASS covers this proposed architecture; no implementation or release pass is claimed.

User clarification: webinar concepts are adapted to app sales, install, onboarding, first value, localized plans, trial, checkout, upgrades and renewal. Do not implement literal webinars or coaching services.
