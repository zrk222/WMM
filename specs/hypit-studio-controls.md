# Spec: hypit-studio-controls
Status: reviewed implementation contract; runtime integration NOT_IMPLEMENTED

## MUST - Functional core
### Description
Bring the complete installed Hypit Studio authoring workflow into WMM for humans
and scoped agents. Use compiled Companion declarations from selected packages as
the control inventory. The current approved-caption adapter remains available;
it does not satisfy this specification. Retain all OpenCut controls required by
`specs/marketer-tool-parity.md`; this Hypit integration does not replace them.

### Requirements (EARS)
- The system shall return an app-owned Studio session against a frozen project, Run, package closure and approved runtime, bind its owned child identity and loopback origin, and reject caller-supplied commands, filesystem roots or network destinations through `owned_session`.
- The system shall return every compiled item and track-object inspector field, its Where/When/How grouping, exact public schema, units, options and write availability to both human and agent clients through `compiled_controls`.
- The system shall store parameter edits only for the current compiled owner and field, validate the author value using the selected package schema and commit a revision-checked source transaction through `parameter_transaction`.
- The system shall store edits only for declared enabled move, trim-start and trim-end gestures using their frame or semantic-domain coordinates and recompile and verify the requested temporal result before accepting the edit through `semantic_timing`.
- The system shall store source edits only within the exact compiled Run and Author closure, retain previous source revisions, and reject stale preimages, linked paths, package-code writes and unapproved runtime changes through `source_transaction`.
- The system shall return actual visual and audio preview, frame stepping, seek, mute, zoom and overlap selection using the compiled rational FPS and playback domain through `media_preview`.
- The system shall expose actual task activity, results and image, video and audio artifacts with stable output identities, pagination and display-name edits through `results_library`.
- The system shall reuse an output only after an explicit accepted build-output selection and shall invalidate affected semantic alignment after speech or dependency changes through `accepted_reuse`.
- The system shall persist time-linked feedback with create, edit, resolve, reopen, delete and seek actions, optimistic conflict checks and agent-visible revision changes through `shared_feedback`.
- The system shall route human, CLI and MCP operations through the same app-owned services with scoped grants, independent checkpoints or current bounded standing approval and revocation through `operation_parity`.
- The system shall restrict both transient preview and durable rendering to the exact approved execution profile, enforce local-only endpoints for the default profile and reject implicit paid fallback or unapproved component execution through `execution_authority`.
- The system shall return actual stage activity, current operation, source and output revision, recovery state and measured elapsed seconds while recording unknown costs and unavailable KPIs explicitly in analytics and PDF reports through `live_reporting`.
- The system shall return an archive containing editable source, selected reusable media, dependency identities and exact video bytes with a checksum manifest and prove a clean offline restoration without credentials or machine-specific private paths through `portable_project`.
- The system shall store drafts and accepted outputs on compilation or observation failure, inspect an uncertain child identity or build before another submission, and close only the owned session and transient execution on cancellation through `session_recovery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: owned_session
  Given an approved project in one app and a selected local runtime
  When `owned_session` is requested with a foreign app, arbitrary origin or executable
  Then no process starts and no foreign files or runtime are opened
Scenario: compiled_controls
  Given different selected packages with scalar, list and record fields
  When `compiled_controls` is read by the human UI and a real agent client
  Then all compiled fields and schemas agree and derived fields remain read only
Scenario: parameter_transaction
  Given a writable parameter and a stale or invalid author value
  When `parameter_transaction` is requested concurrently by human and agent
  Then only the current valid transaction commits and the rejected draft survives
Scenario: semantic_timing
  Given frame and semantic-domain timeline handles
  When `semantic_timing` moves or trims an item
  Then decoded playback and recompiled timing match the requested coordinate and rejected inverse writes roll back
Scenario: source_transaction
  Given the exact current Run and Author source closure
  When `source_transaction` targets a stale source, package file or linked path
  Then the write is rejected without changing the retained source history
Scenario: media_preview
  Given a composition with overlapping visual and audio tracks
  When `media_preview` plays, seeks, steps and mutes at desktop and mobile widths
  Then actual rendered frames and audio follow the composition and selection remains usable
Scenario: results_library
  Given ongoing tasks and finished image, audio and video outputs
  When `results_library` is paged or renamed and refresh then fails
  Then output identities remain exact and the previous readable results survive
Scenario: accepted_reuse
  Given an explicitly accepted output and a revised spoken script
  When `accepted_reuse` creates a variant
  Then unaffected outputs are reused exactly and affected alignment is rebuilt
Scenario: shared_feedback
  Given human and agent clients viewing the same Run
  When `shared_feedback` is changed and a stale update follows
  Then the current comment revision persists and the conflicting update cannot overwrite it
Scenario: operation_parity
  Given owner UI, actual CLI and official MCP clients
  When `operation_parity` runs edits within and outside a grant
  Then receipts agree within scope and foreign, expired, revoked or unapproved edits are denied
Scenario: execution_authority
  Given a default local-only execution profile
  When `execution_authority` encounters a provider request or changed component code during preview or rendering
  Then execution stops before the unapproved effect and no fallback is selected
Scenario: live_reporting
  Given running, failed and recovered owned work
  When `live_reporting` is inspected and exported
  Then UI, durable telemetry and PDF show matching observed stages and distinguish unknown costs
Scenario: portable_project
  Given a completed source-bound project and explicitly selected media
  When `portable_project` is restored in a clean offline workspace
  Then source and media hashes match and the decoded restored video matches the declared render receipt
Scenario: session_recovery
  Given an interrupted session with unsaved edits and an uncertain build
  When `session_recovery` inspects, reconnects or cancels the owned work
  Then no duplicate build is submitted, drafts remain available and foreign processes are untouched
```

## SHOULD - Technical
- Pin the reviewed upstream source separately from the installed executable,
  package closure and runtime profile. A launcher hash alone is insufficient to
  establish the component code that a Studio session will execute.
- Reuse Hypit's schema, mutation and temporal inverse compiler rather than
  reconstruct package semantics in WMM. Never accept caller-supplied source
  ranges or arbitrary endpoint passthrough as an agent mutation API.
- Upstream same-origin checks are an additional local boundary. They do not
  authenticate a WMM app owner or enforce grants and standing approval.
- Preview HTML and media remain untrusted. Do not expose WMM credentials or
  privileged parent-page access to the preview. Determine the required browser
  isolation and media resource route through actual desktop/mobile execution.
- Session/source edits invalidate affected approvals. A saved comment, source
  revision or preview snapshot is not exact-artifact publication approval.

## Evidence and remaining scope
`specs/hypit-studio-source-review.json` pins the inspected upstream files and
specific integration findings. It is source-review evidence only. Studio session
integration, runtime acceptance, complete controls and clean restoration remain
NOT_IMPLEMENTED/NOT_RUN until their own evidence exists. Do not infer provider
savings, performance, growth, completeness or a numerical quality score here.
