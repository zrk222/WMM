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
| Shape and approve the creative / owner and scoped agent | Open a brief from adopted research, choose an approved caption, place rights-reviewed footage and start the exact reserved Hypit render. Review the completed file and save an exact artifact approval with one post slot and a finite call allowance. The same browser tab can recover saved render and artifact approvals after an uncertain response. | Review, schedule and verify actual Facebook delivery separately. | [Research and approval UI](../mission_control/static/organic-research.js), [video editor](../mission_control/static/video-editor.js), [workflow recovery](../mission_control/organic_video_workflow.py) | RESEARCH_TO_ARTIFACT_APPROVAL_GUI |
| Publish the exact output / owner or authorized agent | From an admitted render, save a local intent and draft schedule for the exact video, caption and Page. Activation is a separate owner action. | Verify the scheduled provider workflow against an authorized live Page. | [Intent executor](../mission_control/campaign_video_execution.py), intent-create/read/execute | SCHEDULED_DELIVERY_GUI |
| Recover an uncertain result / approving owner | Reopen delivery from the exact artifact approval to inspect its retained intent and schedule. Request read-only Facebook recovery when the saved state includes a remote video ID. | Inspect outcomes without a remote ID with the provider before any new action. | [Owner routes](../mission_control/organic_video_http.py) | OWNER_RECOVERY_GUI |
| Schedule and stop / current owner | Save, review, activate, inspect or turn OFF a single approved Reel schedule with visible phase-check limits. | OFF stops future scheduled work. Delivery that already occurred is retained. | [Shared scheduler](../mission_control/campaign_schedule.py), [video adapter](../mission_control/organic_video_schedule.py) | OWNER_SCHEDULE_GUI |
| Follow phases and receipts / owner | Show effective state, provider stage, next check, limits, exceptions and retained worker receipts. Export the schedule as JSON or PDF. | Public visibility and measured app outcomes require independent evidence. | [Phase observations](../mission_control/organic_video_monitor.py) | OWNER_PHASE_REPORT_GUI |

The Research GUI covers a single admitted Reel from task intake through owner scheduling and receipt review. The acceptance record distinguishes simulated provider tests from live delivery and measured app outcomes.

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
