# Operational GUI coverage

Owner requirement: founders and teams must operate supported marketing workflows
through the actual WMM application. The public preview and its synthetic sample
are excluded from this acceptance. This matrix records current evidence and
remaining work; a working backend route alone does not close a GUI row.

## Organic video journey — initial source inventory

Reviewed November 4, 2026. This is a source inventory, not a fresh execution
receipt for every screen. The linked tests were inspected by the UI reviewer;
root execution evidence is retained separately for completed backend packets.

| User job / role | Actual GUI today | Missing operational control | Domain path to reuse | Acceptance state |
| --- | --- | --- | --- | --- |
| Find references / owner and scoped collector | Research → Open discovery research reviews saved app references and collections. | Prepare a genre/app research task, select the recipient agent, follow collection and inspect submitted qualification evidence. | [Discovery UI](../mission_control/static/discovery-ui.js), [organic owner routes](../mission_control/organic_video_http.py), collector claim/submit through scoped CLI/MCP | ADJACENT_GUI; ORGANIC_TASK_GUI_MISSING |
| Adopt a result / current owner | Manual saved-source review exists. | Review exact collector results and approve one candidate's adoption with source/baseline/rights provenance. | [Intake](../mission_control/organic_video_intake.py), task-read and intake owner routes | BACKEND_TESTED; GUI_MISSING |
| Agree on production / owner | Existing campaign approval controls cover a separate scope. | Create/read/revoke the organic video policy, show exact sources, claims, templates, destinations, expiry, quotas and remaining capacity. | [Video policy](../mission_control/organic_video_policy.py), owner-only create/revoke; separate agent read/reserve/admit | BACKEND_TESTED; GUI_MISSING |
| Shape the creative / operator and scoped agent | Video projects support editing, history, preview and saved-revision rendering. | Connect the selected research/brief/owned-media workflow to the approved production policy and admitted artifact. | [Video editor](../mission_control/static/video-editor.js), [workflow preparation](../mission_control/organic_video_workflow.py), Hypit and policy admission | EDITOR_GUI_EXISTS; HANDOFF_MISSING |
| Publish the exact output / owner or authorized agent | No organic video intent screen. | Select an admitted render, inspect exact caption/destination/rights, execute within scope and inspect the retained provider stage/ID. | [Intent executor](../mission_control/campaign_video_execution.py), intent-create/read/execute | BACKEND_TESTED; GUI_MISSING |
| Recover an uncertain result / approving owner | Other campaign recovery screens exist. | Inspect the retained original intent and perform permitted read-only recovery without a duplicate send. | intent-read/reconcile through [owner routes](../mission_control/organic_video_http.py) | BACKEND_TESTED; GUI_MISSING |
| Schedule and stop / current owner | Existing post/ad schedule controls use the separate campaign scope. | Prepare, review, activate, inspect and turn OFF an exact Reel schedule with visible phase-check limits. | [Shared scheduler](../mission_control/campaign_schedule.py), [video adapter](../mission_control/organic_video_schedule.py), schedule-* owner routes | SCHEDULE_BACKEND_MERGED_PR84; GUI_MISSING |
| Follow phases and receipts / owner | Existing campaign progress is not bound to organic phase observations. | Show effective state, last observed phase, next check, limits, exceptions and the complete retained worker chain; export the report. | video schedule-status; [phase observations](../mission_control/organic_video_monitor.py) | T14_BACKEND_IN_PROGRESS; GUI_MISSING |

No production static JavaScript binding to `/organic-video/` or
`organic-video.*` was found in this bounded inventory. Adjacent discovery,
editing and campaign tests do not establish this missing end-to-end GUI.

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
