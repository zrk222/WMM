# Spec: commercial-gui
Status: owner-required; operational coverage and acceptance incomplete

## MUST - Functional core
### Description
Deliver Wize Marketing Machine as a complete operational product for founders,
team operators, reviewers and personal agents. Customers direct the work through
the GUI; agents use the same governed domain services. The existing local GUI is
the foundation. The public marketing preview and synthetic sample are separate
artifacts and do not prove production workflows, supported network execution or
commercial adoption.

### Requirements (EARS)
- The system shall return a coverage matrix linking each supported human or agent workflow to its operational screen, role, actions, state, recovery, export and execution proof through `gui_coverage`.
- The system shall return a goal-first onboarding and account-setup wizard that delivers a saved packet without terminal commands, YAML editing or raw grant JSON through `gui_first_value`.
- The system shall return role-aware preparation, editing, review, approval, execution, monitoring, cancellation, recovery and result controls for each supported workflow through `gui_lifecycle`, preserving the human and agent authority contracts.
- The system shall return context, available analytics, a next action, and redacted PDF and JSON reports of each operational page's workflow state, metrics and receipt references through `gui_context`, showing source dates and unknown data without credential values.
- When an operator reviews an agent proposal or creative change, the system shall display current versus proposed content, provenance and revision-bound feedback through `gui_review` without granting publication authority from a creative preference.
- When approval is required, the system shall return the exact current action and its consent scope in a unified owner action center through `gui_approval`, rejecting stale, revoked and wrong-role decisions and applying 0 seconds of grace after the stored authority expiry.
- When automation runs or stops, the system shall show actual recorded stages, activity, quotas, timestamps, exceptions and effective OFF state through `gui_telemetry`, retaining prior receipts and separating queued, prepared, rendered, delivered and measured outcomes.
- The system shall return keyboard-accessible workflows, empty, partial, loading and error states at desktop 1440px and mobile 390px, and capture the native platform acceptance receipts defined by the native client contract through `gui_quality`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: gui_coverage
  Given the current supported operation and workflow catalog
  When the GUI coverage matrix is audited
  Then every user-facing workflow has a real screen and role-appropriate action path with implementation and execution receipts, and missing coverage remains unfinished
Scenario: gui_first_value
  Given a first-time nontechnical operator
  When they create a workspace, add an app or business and follow the first-value path
  Then they open a useful packet without writing commands or configuration files and their elapsed time and friction are recorded
Scenario: gui_lifecycle
  Given an authorized human and a separately scoped agent
  When the actual application performs a campaign workflow through the GUI
  Then the human and agent can use their respective controls from inputs to results and recovery while the same server authority remains enforced
Scenario: gui_context
  Given a page with complete, partial or unavailable source data
  When its explanation and report are opened
  Then the operator understands what it collects, does and delivers and can export relevant evidence without fabricated KPIs
Scenario: gui_review
  Given a media project or agent proposal at a known revision
  When the reviewer compares alternatives or leaves timeline feedback
  Then the resulting edit proposal preserves revision and source hashes and needs its own current execution authority
Scenario: gui_approval
  Given a pending exact effect and a current approving owner
  When approval is accepted, rejected or attempted after a state change
  Then only current authorized approval advances work and the decision retains its actor, scope and receipt
Scenario: gui_telemetry
  Given active, interrupted and stopped automation
  When the operator watches or reopens the actual application
  Then stages, retained effects, effective stop state and actionable recovery remain accurate without duplicate execution
Scenario: gui_quality
  Given the declared desktop, mobile and native platform profiles
  When keyboard, resizing, permissions, offline recovery and report exports are exercised
  Then the application retains focus and usable controls without overflow or hidden authority decisions and captures dated platform evidence
```

## SHOULD - Screen coverage
1. Welcome and first-value onboarding: business/app selection, owner access,
   guided setup, labelled sample choice and the first actual useful packet.
2. Goal home: Set your goal, Watch the work and Review results, with advanced
   controls available when relevant.
3. Workspaces and portfolio: explicit app/client boundaries and authorized
   company aggregation; team roles belong to the hosted isolation contract.
4. Connections and providers: user-owned OAuth/BYOK onboarding, protected storage,
   connection health, permissions, refresh and concrete recovery actions.
5. Research: query, industry/narrative/treatment taxonomy, source inclusion and
   exclusion, viral baseline evidence, UGC intake and saved collections.
6. Creative workbench: app proof, claims, uploads/Drive, media rights, original
   briefs, production settings and Hypit preflight.
7. Editor and creative review: trim, order, stitch, revision history, comparison
   and frame/time-bound feedback for human and agent edits.
8. Campaigns: network-specific supported destinations, exact creative preview,
   organic/paid choice, scheduling and provider result inspection.
9. Automation agreement: agent/team, accounts, effects/content, schedule, expiry,
   quota, currency/budget and stop rules before activation.
10. Live operations: real progression, current activity, waiting observations,
    effective stop status, worker recovery and retained execution IDs.
11. Owner action center: approvals, rejected proposals, expired scope and recovery
    decisions with readable context and separately opted-in notifications.
12. Analytics and results: dated source-backed KPIs, windows, denominators,
    incomplete data, experiment decisions and PDF/structured exports.
13. History and evidence lineage: source to interpretation to brief to artifact
    to effect receipt; operations and causal business outcomes stay distinct.
14. Settings and help: brand/provider preferences, limits, roles, deployment and
    account recovery with progressive disclosure and no hidden costs.

## SHOULD - Implementation and evidence
- Reuse existing Python services, CLI/MCP contracts, worker and local GUI. Add no
  second authorization model or duplicate campaign engine. A framework change
  requires a concrete architectural reason, not an assumed absence of a GUI.
- Use Nanna storytelling and Prestige design on the actual product, not only
  the public preview. Prefer marketer language; inspect hashes in advanced views.
- Maintain a per-workflow matrix with real routes, current implementation state,
  test command, source hash, platform and receipt. Do not count an agent-only API
  as a usable human screen or a screenshot as execution proof.
- Local desktop, optional hosted teams and independent native iPhone/iPad remain
  separate execution profiles with explicit credential residency and acceptance.
  Preserve the existing native spec and the owner's physical-device merge policy.
- GUI readiness supports commercialization; measured utility, outcomes, pricing
  and willingness to pay still need their own evidence.

## Authorized parameters

## Acceptance measurement and authority handoff
- Inventory the current CLI/MCP catalog and application routes by workflow before
  claiming GUI completeness. Each workflow needs a stable ID, human role,
  agent capability, screen/action path, lifecycle/recovery/export states, source
  hashes and dated execution receipts. Unknown or unimplemented rows stay open;
  the initial organic-video matrix is not the complete catalog.
- Human GUI requests use the existing fresh owner session and CSRF controls.
  Agents use the separately scoped CLI/MCP gateway and cannot borrow the browser
  owner session. The GUI assigns permitted tasks, displays agent proposals and
  retained results, and routes owner decisions through existing owner services.
  Test each handoff with current, wrong-role, expired, revoked and changed-input
  cases; displaying an agent result creates no approval or execution authority.
- A first useful packet contains the selected app/business and goal, dated source
  evidence or explicit missing inputs, one evidence-linked proposed action, the
  next required decision, and a saved packet ID that reopens after restart.
  Record elapsed wall time from beginning setup to opening that saved packet,
  completed setup steps and each observed interruption. Keep human first-use
  acceptance NOT_RUN until an actual first-time operator performs it.
- Map each claimed profile to its command/build identity, source hashes, date,
  actor role, expected/observed result and receipt. Desktop web profiles exercise
  1440px and 390px layouts, keyboard review, exports and restart recovery. Native
  iPhone/iPad evidence follows the existing native contract separately; simulated
  browser or desktop evidence cannot close native acceptance.
