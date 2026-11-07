# Plan: goal-first-automation
Spec: specs/goal-first-automation.md
Architect verdict: PASS

## Architecture
Pure frontend projection over current workspace facts. Retain existing routes and authority. Local goal choice is app-scoped presentation only. Backend slices need their own contracts.

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/guided-workflow.js,mission_control/static/app.js,mission_control/static/index.html,mission_control/static/style.css | verify=`node --test tests/goal_journey.test.cjs` | Implement three-choice navigation and app-scoped goal guidance.
- [ ] T2 | slice=tests | files=tests/goal_journey.test.cjs | verify=`node --test tests/goal_journey.test.cjs` | Prove app isolation, unknown preference rejection, storage recovery, source escaping and no automatic effects.

- [ ] T3 | slice=tools | files=tools/test_goal_journey_browser.py | verify=`python tools/test_goal_journey_browser.py` | Exercise default home, explicit selection, advanced tools, app isolation and report in actual desktop/mobile browser.

## Full goal roadmap
1. Goal-first navigation and fixed outcome selection.
2. Outcome setup inventory and repairs through existing Readiness.report.
3. Unified owner-facing agreement wrapping distinct enforced scopes.
4. Persistent approved campaign batches and bounded monitoring, measurement and owner reports through existing worker.
5. Packaged desktop first-use and optional authenticated always-on worker. Preserve standalone native iOS.

## Gates
CF doctor and strict SpecLine/validator/spec/plan seals before implementation. Focused tests, actual desktop/mobile browser, Prestige and hash-bound workflow audit before slice completion. Provider/unattended acceptance awaits its own implementation. Full goal remains active.

## Owner-approved goal additions — 2026-11-02
The owner requested these additions after the original five-part goal. They extend the goal rather than replacing its incomplete requirements. Complete the current setup, agreement and scheduling foundation first, then deliver these using the existing domain services. No item below is implemented merely by being listed here.

| Track | Required behavior | Acceptance evidence |
| --- | --- | --- |
| Connection maintenance | Detect stale/expired access, use only already permitted renewal, show one explicit reconnect action for interactive authentication; never widen scopes or change account. | Expiry/refresh/disconnect races; exact account continuity; secret-free status; actionable reauthentication; actual supported-provider readback separate from fixtures. |
| Creative production batches | Owner-reviewed brief and cleared assets produce finite variants using existing editors/renderers; inspect captions/audio/framing and flag failed checks. | Exact input/rights/brief binding, finite resource reservation, variant lineage, actual output inspection, cancellation/restart and no duplicate renders; automatic publication remains a separate authority. |
| Experiment monitoring | Schedule bounded observations, evaluate completeness/maturity/guardrails and recommend continue/change/stop. | Current declared hypothesis/KPI/window, compatible denominators and source coverage, deduplication and unknown handling, no unsupported causal lift; experiment changes require exact authority. |
| Campaign protection | Reconcile delivery and spend observations, detect configuration drift and pause only through an approved protective path. | Exact saved provider/account IDs, independent safety allowance, delayed-spend labels, drift/expiry/OFF/recovery races, verified pause or PAUSE_UNCONFIRMED; retained commitments are not recycled automatically. |
| Weekly owner reports | Assemble what ran, what changed and what needs the owner, with receipt links, spend observations, KPI coverage and one next action. | Source/hash/date-bound report, previous comparable snapshot only, no secrets or fabricated changes, owner-selected schedule and private destination, no outgoing message without authorized delivery. |
| Agent handoffs | Resume a task through another compatible agent using current app context, operation subset, limits, open jobs and receipt IDs. | Closed handoff schema, current app/policy/catalog/resource revisions, separate scoped grant or verified host path, stale/foreign/revoked rejection, retained request IDs and no duplicated effects; no credential forwarding. |
| Exception inbox | Routine unchanged work stays quiet; material failure, expiry, uncertainty, decision or completion surfaces evidence and a concrete action. | Stable deduplication, source-linked causal history, severity/action prioritization, active/resolved state and recovery, keyboard/mobile accessibility, no manufactured alerts or hidden required decisions. |

### Authority retained for expanded automation
A general toggle does not authorize new networks, newly generated public content, broader account scopes, automatic budget increases or outbound messages. Such effects require implemented validators and an exact owner-approved rule or action. Agent-generated recommendations remain recommendations until authorized execution and receipt readback.

### Completion rule
The goal remains active until both the original five deliverables and these additions have requirement-matched evidence. Keep local synthetic acceptance, actual provider/device acceptance, deployment and measured business outcomes separate. Do not mark the goal complete based on a subset of completed tracks.

## Owner-added channel execution - November 6, 2026
The owner requires Instagram, TikTok, YouTube Shorts and LinkedIn operating workflows alongside Facebook: account connection, content review, exact approval, publication, status reconciliation, monitoring and receipts. This extends the prior Meta-only execution scope. Implement through `specs/multi-channel-publication.md` and `plans/multi-channel-publication.md`; OAuth-only connections or preview labels do not satisfy channel execution. Preserve zero-spend organic defaults and per-channel owner consent. Complete the attributable WizeMe experiment in parallel; channel implementation does not establish marketing gains.
