# Operational GUI coverage

Owner requirement: founders and teams must operate supported marketing workflows
through the actual WMM application. The public preview and its synthetic sample
are excluded from this acceptance. This matrix records current evidence and
remaining work; a working backend route alone does not close a GUI row.

## Organic video journey — current coverage

Reviewed November 4, 2026. Research task and intake controls have actual isolated
owner HTTP and Chromium acceptance at desktop and mobile widths. Remaining rows
are source inventory, not fresh execution evidence for every screen.

| User job / role | Actual GUI today | Missing operational control | Domain path to reuse | Acceptance state |
| --- | --- | --- | --- | --- |
| Find references / owner and scoped collector | Research → Your agent research prepares a bounded task for a selected existing grant, reviews exact scope and lists saved task/results. | Source access must be configured in the collecting agent; a task alone is not a completed external search. | [Research GUI](../mission_control/static/organic-research.js), [owner routes](../mission_control/organic_video_http.py), scoped collector CLI/MCP | GUI_IMPLEMENTED; SIX_SYNTHETIC_BROWSER_SCENARIOS_PASS; LIVE_COLLECTION_NOT_CLAIMED |
| Adopt a result / current owner | Exact source/baseline/rights review, structured evidence card, full confirmation, history, JSON and PDF reports. | Media reuse, production and publication require separate authority. | [Intake](../mission_control/organic_video_intake.py), request-hash readback and retained uncertain-write recovery | GUI_IMPLEMENTED; DESKTOP_AND_MOBILE_ACCEPTANCE_PASS |
| Agree on production / owner | Research → Video production approvals selects rights-reviewed clips, claim text, captions, completed render hashes or standing generation, a tested Page and finite limits. Review, revalidate, recover, revoke and export saved approvals. | Preparation and admission handoff remain separate steps. | [Policy GUI](../mission_control/static/organic-policy.js), [existing policy authority](../mission_control/organic_video_policy.py) | DESKTOP_AND_MOBILE_SYNTHETIC_ACCEPTANCE |
| Shape the creative / operator and scoped agent | Video projects support editing, history, preview and saved-revision rendering. | Connect the selected research/brief/owned-media workflow to the approved production policy and admitted artifact. | [Video editor](../mission_control/static/video-editor.js), [workflow preparation](../mission_control/organic_video_workflow.py), Hypit and policy admission | EDITOR_GUI_EXISTS; HANDOFF_MISSING |
| Publish the exact output / owner or authorized agent | No organic video intent screen. | Select an admitted render, inspect exact caption/destination/rights, execute within scope and inspect the retained provider stage/ID. | [Intent executor](../mission_control/campaign_video_execution.py), intent-create/read/execute | BACKEND_TESTED; GUI_MISSING |
| Recover an uncertain result / approving owner | Other campaign recovery screens exist. | Inspect the retained original intent and perform permitted read-only recovery without a duplicate send. | intent-read/reconcile through [owner routes](../mission_control/organic_video_http.py) | BACKEND_TESTED; GUI_MISSING |
| Schedule and stop / current owner | Existing post/ad schedule controls use the separate campaign scope. | Prepare, review, activate, inspect and turn OFF an exact Reel schedule with visible phase-check limits. | [Shared scheduler](../mission_control/campaign_schedule.py), [video adapter](../mission_control/organic_video_schedule.py), schedule-* owner routes | SCHEDULE_BACKEND_MERGED_PR84; GUI_MISSING |
| Follow phases and receipts / owner | Existing campaign progress is not bound to organic phase observations. | Show effective state, last observed phase, next check, limits, exceptions and the complete retained worker chain; export the report. | video schedule-status; [phase observations](../mission_control/organic_video_monitor.py) | BACKEND_MERGED_PR85; GUI_MISSING |

The Research GUI now binds the owner task and intake routes. Existing editing
and campaign screens still do not establish the remaining end-to-end organic
production, intent, schedule and phase-monitor controls above.

## Keyword and competitor evidence

Results → Subscription growth review → Import keyword research accepts a local
agent-prepared JSON packet. Its review, immutable save, source/phrase readout,
JSON download and actual PDF generation pass product-browser acceptance at
1440px and 390px. Existing scoped CLI/MCP growth.save/read use the same store.
See [market research](market-research.md). These are supplied source snapshots;
live search-volume/rank collection and measured marketing outcomes are separate.

## Existing foundations to preserve

The main application routes include goal overview, guided workflow, pipeline,
evidence, results, connections, agent access, activity, research and weekly
exceptions in [app.js](../mission_control/static/app.js). Use these entry points
and their existing server controls rather than introduce another campaign engine
or expose a generic raw-API console as the commercial GUI.

Existing tests to extend include discovery_ui.test.cjs, video_editor.test.cjs,
campaign_schedule_ui.test.cjs and the owner/agent HTTP and browser suites. New
organic workflow acceptance needs actual rendered controls, role-negative tests,
current hash/revision review, Stop/recovery, exports and real source-bound data.

## Full product coverage still to audit

The complete screen contract is [commercial-gui.md](../specs/commercial-gui.md).
Onboarding, account/provider setup, multi-app/team roles, broader networks,
creative comparison, approval action center, evidence lineage and every report
need their own lifecycle/role/platform rows and receipts. Uninventoried coverage
remains unfinished. Screenshots and synthetic walkthroughs cannot close live
execution, platform, analytics or measured-outcome acceptance.
