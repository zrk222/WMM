# Spec: creative-production-batches
Status: draft

## MUST - Functional core
### Description
Allow an owner to review and run a finite set of original video variants from current proof-bound briefs while preserving separate publication authority and local execution limits.

### Requirements (EARS)
- The system shall return 1 to 8 exact brief and shape variants, a selected desktop or iOS runtime and an expiry within 24 hours under one selected app through `finite_plan`.
- The system shall bind each variant to current manifest version, brief hash, screen hashes and rights proof through `source_binding`.
- When a reviewed plan is admitted, the system shall reserve its total frame count atomically within the active app limit through `reservation`.
- When a saved batch resumes, the system shall return one job per variant by reusing its deterministic child request key through `deduplication`.
- If a batch is cancelled, the system shall reject new child admission and cancel owned outstanding jobs through `cancellation`.
- When output exists, the system shall return actual byte inspection of audio, frame dimensions and caption or visual uncertainty through `inspection`.
- The system shall show prepared, queued, rendered and review-needed states with no publication authority through `authority`.
- When an owner or agent admits a reviewed batch, the system shall store a hash-bound authority reference without a bearer credential and reject a stale or foreign app, owner, action, grant or standing approval through `agent_scope`.
- When a native iOS owner or agent runs an admitted batch in the foreground, the system shall render the exact approved stills and captions through the on-device native renderer and store the decoded artifact through `native_capability`.
- When a native iOS render resumes or finishes, the system shall reject changed source proof, cancelled work or invalid authority through `native_recovery`.
- The system shall show the owner each exact variant, frame reservation, state and human review requirement before or after admission through `batch_ui`.
- When an owner selects an app-owned PNG or JPEG still on iOS, the system shall decode and store the actual image locally with rights and authenticity unconfirmed through `native_still_intake`.
- When an owner or agent provides explicit source observations, production capability, proof and rights, the system shall store those declarations and prepare an original brief using existing validation through `native_first_use`.
- When an owner selects an unpublished owned still, the system shall store its app-scoped asset identity and current rights-cleared byte hash as a local source with unknown metrics through `owned_source`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: finite_plan
 Given an owner selects 1 to 8 brief and shape variants, a local runtime and an expiry within 24 hours
 When `finite_plan` checks the declared transition
 Then the plan contains exactly those variants, runtime, expiry and frame totals
Scenario: source_binding
 Given a manifest or brief or rights proof changes
 When `source_binding` checks the declared transition
 Then admission or rendering rejects the stale plan
Scenario: reservation
 Given active reservations and a finite frame limit
 When `reservation` checks the declared transition
 Then concurrent admission cannot exceed the limit
Scenario: deduplication
 Given a restart after child admission
 When `deduplication` checks the declared transition
 Then each variant retains at most one child job
Scenario: cancellation
 Given a queued or running batch
 When `cancellation` checks the declared transition
 Then no later child is admitted and outstanding owned jobs are cancelled
Scenario: inspection
 Given an actual saved rendered artifact
 When `inspection` checks the declared transition
 Then verified metadata and unknown caption or framing review are reported separately
Scenario: authority
 Given a prepared or rendered variant
 When `authority` checks the declared transition
 Then publication remains unexecuted and separate
Scenario: agent_scope
 Given a stale or foreign agent grant
 When `agent_scope` checks the declared transition
 Then the protected action is denied
Scenario: native_capability
 Given an admitted iOS batch with rights-cleared stills
 When `native_capability` checks the declared transition
 Then the foreground native renderer creates and decodes each selected variant without desktop services
Scenario: native_recovery
 Given a cancelled, interrupted or stale native batch
 When `native_recovery` checks the declared transition
 Then completion is rejected or reconciled without a duplicate render
Scenario: batch_ui
 Given an owner reviews a finite batch
 When `batch_ui` checks the declared transition
 Then exact variants, frame total, progress and required human review are visible
Scenario: native_still_intake
 Given an owner selects an actual PNG or JPEG on this device
 When `native_still_intake` checks the declared transition
 Then the bounded decoded bytes are stored without an inferred rights approval
Scenario: native_first_use
 Given explicit owner-provided source observations and existing app proof
 When `native_first_use` checks the declared transition
 Then the existing source, analysis, capability and brief services validate the declarations without invented metrics or rights
Scenario: owned_source
 Given an unpublished app-owned still with current explicit rights and authenticity
 When `owned_source` checks the declared transition
 Then the source binds its actual local asset without asserting a public URL or viral qualification
```

## SHOULD - Technical
- Reuse the existing render queue and proof checks with a deterministic key; retain cancellation and crash recovery.
- Reuse the existing owner and agent admission checks, persist only hash-bound authority references, and recheck authority at child admission and artifact commit without restoring process-local context.
- Native iOS uses the embedded Python domain, foreground AVFoundation and trusted native byte inspection. Extend its source resolver only as needed for exact rights-cleared still images. Native foreground work does not promise background execution.
- Owned local source references use a typed asset identity rather than an invented public URL; they bind the same app, current file hash and current owner-supplied rights. Discovery qualification rules are unchanged.
- Use isolated temporary workspaces for tests; preserve existing user files and no provider or publishing calls.
- Report absence of measurable visual or caption proof as unknown and require human review.

## Authorized parameters
MAX_VARIANTS = 8
MAX_ACTIVE_FRAMES = 11520
FRAME_RATE = 24
MAX_BATCH_HOURS = 24
INSPECTION_TIMEOUT_SECONDS = 30
TEST_FRAME_BUDGET_MIN = 1
TEST_FRAME_BUDGET_EXAMPLE = 2880
timeout = 30
max_total_frames = 1
max_total_frames = 2880
max_total_frames = 1440
MAX_IMAGE_BYTES = 8388608
max_calls = 5
max_workers = 2
