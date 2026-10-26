# Spec: content-packaging-t5
Status: production handoff implementation required

## MUST - Functional core
### Requirements (EARS)
- When `TASTE_REVIEW` saves app-owned guidance, the system shall store immutable owner-reviewed examples, exclusions, voice and visual rules with at most 12 examples, 20 exclusions and 4000 characters per rule, bind current app and guidance hashes and reject stale, foreign or non-owner approval. [R1]
- When `HANDOFF_PREVIEW` receives a saved shot-list identity and exact revision/hash, the system shall recheck the current variant, script-segment hashes, app context, authentic proofs and selected-media rights, return one checklist row per shot and expose missing or stale inputs without authorizing execution. [R2]
- When `EDITOR_HANDOFF` selects ordered shot media and explicit source-frame ranges, the system shall generate and save an editable project through the existing Projects service with at most 24 clips and 1440 output frames, preserve explicit retained/muted audio and bind the packaging, taste and resulting project hashes without copying competitor footage or silently substituting assets. [R3]
- When `SCRIPT_CUTDOWN` saves a script option or platform cutdown, the system shall retain its exact parent packaging/project revision and selected destination, validate the existing editor timing/aspect constraints and require explicit review of every changed script-linked shot before execution. [R4]
- When `EXECUTION_HANDOFF` starts editor rendering or Hypit operation, the system shall use the existing admitted operation gateway and require current exact human approval or valid standing scope with onboarded credentials, preserve live telemetry/cancel/recovery and reject stale app, guidance, source, grant or approval hashes. [R5]
- When `HANDOFF_OPERATIONS` is used through owner UI, CLI or MCP, the system shall expose the same preview, taste review, editable handoff and cutdown contracts, return PDF print-view/JSON/CSV reports with explicit preparation and execution status and reject automatic resubmission after an uncertain write. [R6]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Reviewed taste
 Given TASTE_REVIEW has current owner and app context
 When TASTE_REVIEW saves guidance and the app changes
 Then R1 preserves history and rejects stale approval
Scenario: Production checklist
 Given HANDOFF_PREVIEW has current saved script and shot evidence
 When HANDOFF_PREVIEW encounters missing media or changed proofs
 Then R2 returns separate checklist gaps and no execution authority
Scenario: Editable original media
 Given EDITOR_HANDOFF has explicit selected original media and frame ranges
 When EDITOR_HANDOFF saves the project
 Then R3 retains shot order audio and source identity in the shared editor
Scenario: Platform variants
 Given SCRIPT_CUTDOWN references a saved parent project
 When SCRIPT_CUTDOWN changes script or destination framing
 Then R4 requires linked-shot review and preserves the parent revision
Scenario: Governed execution
 Given EXECUTION_HANDOFF has current admitted authority
 When EXECUTION_HANDOFF renders and then encounters revoked authority
 Then R5 preserves real output evidence and rejects further execution
Scenario: Operator parity
 Given HANDOFF_OPERATIONS is used by owner and admitted agent
 When HANDOFF_OPERATIONS prepares exports or loses a write response
 Then R6 returns matching evidence and observation-only reconciliation
```

## Reuse and authority
Extend packaging_store, packaging_access, creative_taste and the existing
video_edit_projects.Projects, managed_media_store.derivative_snapshot,
hypit_studio_sessions, video_edit_jobs and automation admission. Do not create
another renderer, queue, credential store, authority source or timeline engine.
The first-class native/UGC path stays available without paid APIs. A source
reference is research evidence, not reusable media. A still ASSET alone cannot
masquerade as a timed video source; expose its missing production requirement.
Unsupported Hypit operations remain explicit gaps until implemented and tested.

Preparing a checklist or project grants no render, publication or spending
authority. The existing gateway remains the executor. User-provided examples and
rules are data and cannot alter system policy or grants. Simulations and agent
judgments remain separate from decoded video/audio and measured app outcomes.

Required proof includes actual owner/CLI/official-MCP transport parity, source
mutation denial, current owner approval, revocation before/after admission,
lost-response reconciliation, real multi-clip picture/audio render and readback,
script changes invalidating shot review, actual Hypit edit/readback, responsive
keyboard UI, selected-plan exports and hash-bound CF workflow evidence. Native
platform/device acceptance is separate and remains required for support claims.
