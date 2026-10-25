# Spec: hypit-public-sessions
Status: draft

## MUST - Functional core
### Description
Connect the installed owned Studio process, parameter broker, durable source
ledger and request-local authority to actual human HTTP and agent CLI/MCP calls.
Each call is app scoped and freshly admitted. Expose an execution summary before
starting Studio; native execution is never authorized by merely reading a page.
The complete Hypit/OpenCut editor and marketer matrix remain parent requirements.

### Requirements (EARS)
- The system shall return a source and installed-runtime execution summary without starting native work through `session_plan`.
- The system shall store one immutable startup reservation per app and request key before creating its private folder or starting native work through `session_reservation`.
- The system shall reject startup if the reviewed source job app manifest current rights installed identity or execution summary changed through `session_start_scope`.
- The system shall admit native start read edit inspect and close only inside the exact authenticated protected operation through `session_authority`.
- The system shall reject revoked authority or changed source inputs before native dispatch during observations of at most 2 seconds and in result transactions through `session_live_authority`.
- The system shall return opaque compiled controls and durable source heads through shared human and agent operations through `session_controls`.
- The system shall return UNKNOWN for unconfirmed native edits including identical retained uncertain retry receipts with 0 additional sends and a mutation deadline of 20 seconds through `session_uncertainty`.
- The system shall reject reuse of startup keys with changed input and return retained matching startup state without another native start through `session_once`.
- The system shall return retained metadata after Service restart as inspection required without adopting saved PIDs URLs or native execution authority through `session_restart`.
- The system shall close only its actual owned selected-app session after current caller admission and retain cleanup requirements after failed startup or shutdown through `session_cleanup`.
- The system shall reject caller-selected folders endpoints PIDs executable arguments source paths or identity claims through `session_private`.
- The system shall reject new startup beyond 2 live sessions per app or 4 live sessions in the local service while leaving admitted cleanup available through `session_capacity`.
- The system shall reject release of retained capacity until a current selected-app cleanup observation proves the exact private child and worker stopped through `session_reconcile`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: session_plan
  Given a current approved app-owned Hypit source job
  When `session_plan` prepares its execution summary
  Then the summary names source runtime effects and limits without a child launch
Scenario: session_reservation
  Given concurrent startup requests for one retry key
  When `session_reservation` stores exact immutable inputs
  Then one reservation exists before any native work starts
Scenario: session_start_scope
  Given a changed source manifest rights or installed runtime
  When `session_start_scope` validates the reviewed execution summary
  Then startup rejects without launching native work
Scenario: session_authority
  Given a human owner or admitted ordinary reviewed or standing agent
  When `session_authority` binds its exact operation
  Then only that operation and selected app session are accessible
Scenario: session_live_authority
  Given revocation cancellation or source change during native work
  When `session_live_authority` rechecks before dispatch and commit
  Then no confirmed result is attributed beyond current authority
Scenario: session_controls
  Given a running owned session
  When `session_controls` reads and edits a writable compiled field
  Then human and agent clients observe the same durable source head
Scenario: session_uncertainty
  Given a lost response or an already uncertain retained edit
  When `session_uncertainty` receives an identical retry
  Then outer execution requires inspection and no native edit is resent
Scenario: session_once
  Given a retained startup reservation
  When `session_once` receives matching or changed startup inputs
  Then matching input returns state and changed input rejects without native start
Scenario: session_restart
  Given retained startup metadata but no live owned object
  When `session_restart` lists or inspects the session
  Then it reports inspection required and never adopts a saved process
Scenario: session_cleanup
  Given a failed startup or revoked in-flight session
  When `session_cleanup` runs owned internal shutdown
  Then verified owned cleanup or an explicit unresolved cleanup state is retained
Scenario: session_private
  Given a private path endpoint PID or caller identity in input
  When `session_private` validates the closed operation schema
  Then it rejects before native execution
Scenario: session_capacity
  Given the live session ceiling is reached
  When `session_capacity` receives another startup
  Then it rejects startup and leaves owned cleanup available
Scenario: session_reconcile
  Given retained unconfirmed startup or cleanup metadata after Service restart
  When `session_reconcile` receives a current cleanup observation and exact registry revision
  Then only verified stopped resources release retained capacity and no saved PID grants shutdown authority
```

## Authorized parameters
LIVE_SESSIONS_PER_APP = 2
LIVE_SESSIONS_PER_SERVICE = 4
STARTUP_SECONDS = 45
READ_SECONDS = 2
MUTATION_SECONDS = 20
COMMAND_SECONDS = 120
MAX_MUTATION_BYTES = 1048576
MAX_RESPONSE_BYTES = 8388608

## Public operation contract
All operations use the existing closed envelope with app_id, operation, input
and resource_id only when declared. Startup is a native local execution effect.
Preparation and listing cannot launch a process or change source.

| Operation | Input | Resource | Result |
| --- | --- | --- | --- |
| studio.plan | source_job_id, manifest_version | none | Current summary and content hash; no startup |
| studio.start | source_job_id, manifest_version, summary_hash, request_key | none | Retained session identity/state; current controls only if live |
| studio.sessions | empty object | none | Bounded selected-app session states and recovery requirements |
| studio.read | empty object | session ID | Current opaque controls and exact source head |
| studio.edit | request_key, base_version, base_hash, parameter | session ID | Verified result or UNKNOWN inspection requirement |
| studio.inspect | empty object | session ID | Observed controls/hash and retained attempts; no resend authority |
| studio.close | empty object | session ID | Verified owned close or explicit cleanup requirement |
| studio.reconcile | registry_version, cleanup_observation_hash | session ID | Terminal cleanup state only after fresh exact stopped-resource proof |

Parameter fields are exactly revision, view_hash, owner_id, field_id and value,
using the existing compiled ControlView. Public startup summary binds app revision
and hash, immutable source job data hash, selected current rights, installed
fingerprint, private local execution profile, ceilings and effect descriptions.
Never expose executable paths, raw native IDs, Studio origin, private source text,
process handles, diagnostics or credentials in public operation results.

Human routes use fresh verified identity and current OWNER role, then bound_owner
and protected. Agent routes reuse ordinary/reviewed/standing dispatch and protected.
The broker callback compares exact action/project/body with the current frozen
operation and performs a protected connection check on every callback. Each new
request binds new authority; a live session does not carry prior execution rights.
Current rights/source validation runs on observations as well as startup, while
owned internal cleanup remains possible after revocation. Public close still
requires current selected-app ownership and may not use a session ID as authority.

## Durable state and recovery
Retain checksum-bound source/summary/request hashes and monotonically transitioned
startup states. Reserve before folder creation or process launch. Keep actual live
objects only in the owning Service manager under a lock. Persisted metadata is
inspection evidence, never permission to adopt a PID or run a native command.
All startup retries return retained state, including PREPARED or unconfirmed
outcomes; they never start another worker implicitly. Changed-key inputs reject.
Startup/close result persistence failure must not cause another launch or claim
confirmed cleanup. Unresolved cleanup remains visible and blocks capacity reuse
until the actual owned child/runtime is confirmed stopped.

Capacity counts every nonterminal reservation in the datastore, including
PREPARED, ACTIVE, closing, UNKNOWN and cleanup-required records, across all manager
instances and Service restarts. Only confirmed terminal cleanup releases a slot.
Reading a missing live object or starting a new Service never clears capacity.
Inspection after restart may run a freshly admitted read-only observer against
the exact checksum-bound private profile/runtime identity and pinned installation.
It may inspect OS ownership and fixed native status; it cannot adopt a PID, launch
another session, or issue shutdown against an unowned worker. Treat missing,
stale, foreign, inconsistent or unreachable runtime evidence as UNCONFIRMED.
Reconciliation accepts only the current inspector's exact stopped-resource proof,
registry revision and app/session identity, rechecks it in the transition and
appends history. A human assertion or arbitrary evidence hash is insufficient.
If stop cannot be proven, show explicit manual-cleanup guidance and retain the
capacity reservation; do not silently clear it to unblock a new startup.

Define a narrow internal outcome finalizer for authority-loss recovery. After
leaving protected request context, the owning manager may append a startup/close
outcome only for its previously reserved exact object/attempt and current registry
version. It may record UNKNOWN or cleanup state and fixed receipts, never alter
source/approval inputs, grant rights, start, edit, adopt or issue unowned shutdown.
Internal cleanup of actual owned objects remains possible after revocation.
If finalizer persistence fails, retain an in-memory unresolved receipt and keep
the durable nonterminal reservation counted; report persistence as unconfirmed.
Test revocation plus failed cleanup plus a failed finalizer write independently.

Startup and close use the same explicit EffectUncertain classification as edits
when a child may exist or teardown/result persistence is unconfirmed. Outer
reviewed and standing outcomes remain UNKNOWN/reconciliation-required, including
matching startup retries. A retained close receipt means SUCCEEDED only when the
exact owned child and private worker are confirmed stopped and final state is
durably recorded. A confirmed native result with a lost public response can be
read from its retained receipt; it never permits another native startup.

All eight operations reach the same long-lived server Service manager. CLI/MCP
clients use the existing loopback operation transport; a short-lived CLI/MCP
process cannot create an independent reusable native manager. Shutdown first stops
new admission, coordinates admitted in-flight calls, closes actual owned objects,
records confirmed or unresolved cleanup, and finally releases server resources.
Reserve registry capacity atomically; serialize individual sessions separately.
Never hold the manager-wide lock across compilation, native commands or HTTP.
Factory startup uses a newly created isolated project and fresh private runtime
from validated frozen source inputs; it never reuses a render job's runtime folder.

For edits, preserve broker intent-before-send ordering and ledger-before-adoption
ordering. Translate both EffectUncertain and retained PREPARED/UNCERTAIN retry
results to explicit uncertain outcomes at the outer review/standing boundary.
APPLIED and verified REJECTED retry results remain inspectable without resend.
Do not infer native rollback from HTTP rejection alone. Retain source versions
and recorded attempts even when startup admission or source freshness later fails.

## Parent acceptance remains mandatory
The approved-brief source profile can bootstrap a real integrated session. It
does not replace selected-agent original authoring, arbitrary approved project
closure import, semantic timing/source transactions, sound, results/reuse,
timestamped feedback, private preview, portable restore/export, telemetry/PDF,
complete dynamic UI controls or the full OpenCut/marketer workflow requirements.
None is waived or marked complete by this session packet. No production provider
activation, publication or spending is authorized by these local operations.
