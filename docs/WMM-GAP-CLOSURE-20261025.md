# Validated WMM gap closure — 2026-10-25

Both supplied reports have been reviewed against current source. This is added to the existing active upgrade goal; all earlier UPG, Hypit/OpenCut, marketer, KPI, viral-discovery and approval requirements remain. Static source review establishes capability presence, not rendered UX quality or production acceptance.

## Corrections to the report baseline

- Guided onboarding, stage explanations and next-step guidance exist; progressive density remains a gap.
- Portfolio weekly exceptions already exist; active-work/readiness breadth remains partial.
- Structured snapshot export/import already exists; reusable structure-only templates remain missing.
- Selected-field website discovery approval exists; wider agent proposal parity remains partial.
- ASC reads and social status/recovery paths already exist; inventory gaps instead of treating providers as absent.
- General process code has POSIX support; native detection/vault/owned Studio parity is not cross-platform.

## Authorized implementation and acceptance

### Platform

**FR-1.1 · P0 · Protected macOS and Linux credentials · MISSING**

Current: Windows Vault explicitly rejects non-nt.

Apply: Add native backend parity with app/database namespace binding and no plaintext fallback.

Acceptance: Real macOS Keychain and Linux Secret Service roundtrip/rotation/delete, unavailable-service denial and snapshot exclusion.

**FR-1.2 · P0 · Cross-platform native agents · PARTIAL**

Current: Discovery paths select Windows executables; generic process code has POSIX support, Studio ownership is Windows-only.

Apply: Add reviewed per-OS CLI identity and owned process-tree controls; do not call POSIX process spawning complete parity.

Acceptance: Real installed Codex/Claude detection, safe profile, version drift, cancellation and descendant cleanup on each OS.

**FR-1.3 · P0 · No plaintext fallback · EXISTING_INVARIANT**

Current: Current Vault fails closed.

Apply: Preserve invariant across new backends and providers.

Acceptance: Secret sentinel absent from files/logs/exports; missing vault rejects rather than downgrades.

**FR-1.4 · P0 · Visible capability matrix · PARTIAL**

Current: Windows-specific setup explains its requirement, but a consistent platform matrix is absent from inspected surfaces.

Apply: Show supported, unavailable and untested capabilities with one concrete setup/recovery action.

Acceptance: Windows/macOS/Linux capability snapshots agree with actual adapter availability and rendered setup.

### Onboarding

**FR-2.1 · P0 · Progressive introduction · PARTIAL**

Current: Guided workflow and next action already exist; guidedView renders every stage by default.

Apply: Lead with current recommended work; keep full workflow and blockers explicitly accessible.

Acceptance: Fresh/resumed/complete apps show focused stage, discoverable full steps, stable progress and no concealed critical findings.

**FR-2.2 · P0 · Stage purpose and acceptance · PARTIAL**

Current: Descriptions, direct missing inputs and verify text already exist.

Apply: Make purpose, needed input, delivered artifact and verification consistently scannable.

Acceptance: Every stage has plain-language purpose/input/deliverable/acceptance and keyboard-accessible detail.

**FR-2.3 · P0 · Separate preparation approval execution outcomes · PARTIAL**

Current: Current guided classification and copy separate input readiness from release approval.

Apply: Use consistent visible evidence-state labels across onboarding, reviews and results.

Acceptance: Operators can distinguish prepared, approved, executed and independently observed states in desktop/mobile tasks.

**FR-2.4 · P1 · Isolated synthetic starter · PARTIAL**

Current: Synthetic tests/examples exist; a dedicated user-facing complete starter journey is not established.

Apply: Add explicitly synthetic isolated starter without changing real workspace evidence or credential bindings.

Acceptance: Starter creation/reset/export never copies authority and cannot satisfy a real-app readiness gate.

### History

**FR-3.1 · P0 · Unified event chronology · PARTIAL**

Current: Audit rows, checkpoints, job events and source histories exist separately.

Apply: Join app-owned proposal/approval/execution/tracking/recovery references with causal links where recorded.

Acceptance: Chronological/causal events reconstruct a complete workflow; absent links stay absent, not inferred.

**FR-3.2 · P0 · Linked provenance · PARTIAL**

Current: Domain receipts already carry hashes and IDs; unified navigation is missing.

Apply: Link timeline events to original app-owned current or historical receipt.

Acceptance: Exact source/hash readback, stale/missing-source state, foreign-app denial and no secret payload leakage.

**FR-3.3 · P0 · History type/status filters · MISSING**

Current: No unified filtered timeline was identified in the inspected surfaces.

Apply: Add bounded cursor pagination and type/status filters to shared human/agent history reads.

Acceptance: Filter consistency, stable pagination and explicit incomplete coverage on realistic synthetic histories.

**FR-3.4 · P1 · Browser-independent local awareness · MISSING**

Current: Worker telemetry is present; no local OS notification/tray channel was identified.

Apply: Add opt-in local terminal/expiry/recovery notices with deduplication and quiet defaults.

Acceptance: With browser closed, supported OS notices reflect durable actual state; denied permission, dismissal and restart do not duplicate.

**FR-3.5 · P0 · Cross-app active work · PARTIAL**

Current: Weekly portfolio exceptions already exist, but complete active sequence/approval coverage is not present.

Apply: Extend existing weekly projection with active jobs, sequences, expiring approvals and prioritized next actions.

Acceptance: App coverage/cursors, failures and timestamps remain explicit; no unobserved zero or global success.

### Review

**FR-4.1 · P1 · Current versus proposed comparison · PARTIAL**

Current: Website setup already shows saved values and editable suggestions.

Apply: Generalize exact field diffs to supported agent proposal types.

Acceptance: User sees old/new/current scope; intervening edits invalidate approval.

**FR-4.2 · P1 · Per-field provenance · PARTIAL**

Current: Setup source fingerprints and suggestion labels exist.

Apply: Standardize public-source/agent/human provenance and source excerpts or references.

Acceptance: No private reasoning disclosure; each field traces to recorded evidence or an explicit unsupported suggestion.

**FR-4.3 · P1 · Selective exact approval · PARTIAL**

Current: Website setup already supports selected-field approval.

Apply: Extend selection to other typed proposal domains by producing a newly bound exact approved subset.

Acceptance: Subset hash/version/expiry validated; dependency/conflict changes require a new review; never silently approve remaining fields.

**FR-4.4 · P1 · Repeated keyboard review · PARTIAL**

Current: Dialogs and some focus restoration exist; no end-to-end repeated-review efficiency proof.

Apply: Improve keyboard sequence, conflict navigation and focus return without default approval.

Acceptance: Keyboard-only repeated review and cancellation across desktop/mobile; focus never escapes or activates approval implicitly.

### Results

**FR-5.1 · P1 · Observed versus missing · PARTIAL**

Current: Tracking already returns observed_counts/flag_findings and explicit failure states.

Apply: Project observed/missing/mismatched/stale evidence into a clear decision surface.

Acceptance: Partial data/zero/missing/unavailable remain distinct; no causal or sample-size inference.

**FR-5.2 · P1 · Counts are not causal lift · EXISTING_INVARIANT**

Current: Current tracking copy explicitly says flag evaluation is not a confirmed view.

Apply: Keep warning and metric definitions adjacent to every new comparison/chart.

Acceptance: No chart or export converts provider distinct IDs into humans/exposures/conversions/lift.

**FR-5.3 · P1 · Durable experiment decisions · PARTIAL**

Current: Experiment lifecycle and growth/customer review records already retain decisions/results.

Apply: Add convenient linked human notes where missing and expose their immutable history.

Acceptance: Note save/reopen/history/export and exact experiment/source links; human note is not provider verification.

**FR-5.4 · P1 · Instrumentation integration state · PARTIAL**

Current: Package generation/download and source-bound validation exist; in-system installation/probe progression is incomplete.

Apply: Track generated/downloaded/reported-installed/probe-observed separately with guided next steps.

Acceptance: Download never means installed; attestation never means verified delivery; exact live probe identity/time/scope retained.

### Portfolio

**FR-6.1 · P0 · Portfolio readiness and active sequences · PARTIAL**

Current: Weekly inbox already evaluates five apps per page with explicit coverage.

Apply: Extend rather than replace with current stage, high-priority gaps and active sequence counts.

Acceptance: Full paginated app coverage, unavailable app handling, source timestamps and no comparison of incompatible metrics.

**FR-6.2 · P2 · Structured export/import · EXISTING_CAPABILITY**

Current: Store.export/restore already implement app snapshot validation and authority exclusions.

Apply: Reuse and document current capability; add scoped structure-only import if needed for templates.

Acceptance: Roundtrip version/hash validation and explicit authority exclusions; do not reimplement snapshot machinery.

**FR-6.3 · P2 · Reusable workspace templates · MISSING**

Current: No curated/user structure-only workspace-template mechanism identified.

Apply: Add versioned non-credential templates with selection preview and conflict handling.

Acceptance: New app identity, no secrets/approval grants/verified evidence/source event IDs copied; examples remain synthetic.

### Providers

**FR-7.1 · P1 · Connection health and scope recovery · PARTIAL**

Current: Protected connection setup, social flows and source-progress recovery already exist.

Apply: Unify health/current scope/expiry/last read/failure/next action in context.

Acceptance: Each supported provider shows current observed state and one exact recovery path; login is not analytics permission.

**FR-7.2 · P0 · Prioritized recovery · PARTIAL**

Current: Guided next actions and weekly recovery cards exist.

Apply: Use common action projection and deep links across empty/error/stale/expired states.

Acceptance: One highest-priority actionable recovery, preserved drafts, exact affected source and stale-action rejection.

**FR-7.3 · P2 · Additional read integrations · PARTIAL**

Current: App Store Connect reviews/catalog and Apple Ads report reads already exist; not solely Play/PostHog.

Apply: Inventory missing requested ASC/analytics reads and implement demand-backed read-only adapters under exact consent.

Acceptance: Official provider contract and account readback, app/scope/page bounds, source hashes, approval expiry and error recovery; no broad provider capability claim.

### Ux

**FR-8.1 · P0 · Actionable empty/error states · PARTIAL**

Current: Nanna stories, guided next action and many recovery dialogs exist.

Apply: Audit every page/state for one concrete prioritized next action.

Acceptance: No dead end, no success on failed source; source-bound action retains user inputs and cancels safely.

**FR-8.2 · P1 · Keyboard/focus consistency · PARTIAL**

Current: Dialog focus support exists in individual paths; global optimized parity is unproven.

Apply: Apply shared initial focus, trap, Escape, return-focus and async stale-dialog handling.

Acceptance: Keyboard/screen-reader repeated flows, no destructive default focus and no detached dialog focus after app switch.

**FR-8.3 · P0 · Scannable evidence states · PARTIAL**

Current: Existing labels and non-claim copy are distributed across pages.

Apply: Use consistent text+shape/icon semantics in pages/reviews/timeline/PDF.

Acceptance: Not color-only; prepared/approved/executed/observed/unknown understandable at a glance and in export.

**FR-8.4 · P1 · Desktop/mobile workflow parity · PARTIAL**

Current: Existing rendered desktop/mobile proofs cover several flows; not every new flow.

Apply: Extend real browser acceptance for each changed critical flow.

Acceptance: Actual desktop/mobile no overflow, touch/keyboard usable, focus preserved, PDF readable; report untested flows explicitly.

## Delivery sequence

1. P0 progressive onboarding, action hierarchy and evidence-state language using existing guided components
2. P0 native vault/agent platform parity with real OS acceptance tracks
3. P0 unified causal timeline and extended existing portfolio active work
4. P1 exact diff/provenance/selective review and repeated keyboard flows
5. P1 opt-in local notifications, uncertainty-preserving result visualization and instrumentation state
6. P2 safe reusable templates and demand-backed read integrations

## Required boundaries

- The report non-goal about a general creative suite does not remove already authorized complete Hypit/OpenCut/marketer controls.
- No automatic publication/spend is newly authorized; existing explicit standing human scope remains governed by its own exact approval, not removed by this report.
- OS credential/process acceptance requires real macOS/Linux execution; Windows mocks cannot prove it.
- No extra analytics provider is selected without current product demand and a bounded official interface.

All31 functional requirements and six nonfunctional requirements are mapped in [the source-bound review](../specs/wmm-gap-closure-review.json). Every missing/partial item remains required; existing capabilities are preserved and extended. No gap is complete from this document. Measure onboarding/review task time, abandonment, reconstruction errors and usage only after collecting an actual baseline and consented user observations. No99%/96% quality score or growth/savings claim is inferred.
