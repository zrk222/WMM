# Spec: hypit-studio-process
Status: draft

## MUST - Functional core
### Description
Implement the owned process adapter required by hypit-studio-controls. The caller
is a trusted WMM service that has already approved the exact app/project source
bundle and supplies a fresh authority callback. This internal adapter is not an
HTTP endpoint or grant admission service. Do not expose its private snapshots,
origins or filesystem identities directly to human/agent clients.

### Requirements (EARS)
- The system shall reject changed installation or frozen project bytes and nonlocal runtime profiles before starting a Studio child through `studio_preflight`.
- The system shall reserve one retained control directory before invocation, start only adapter-owned arguments on IPv4 loopback and reject another automatic start against a retained attempt through `studio_owned_start`.
- The system shall return actual compiled session snapshots only while owned child and caller authority remain current, require the independently approved Author root and exact compiled-source set, and reject redirects, foreign source, more than 8 MiB response bytes or 1 MiB server logs through `studio_read`.
- The system shall stop only its live owned child tree and shut down only its unchanged private runtime profile and bound directory identities, rejecting links or reparse points and requiring the actual stopped receipt through `studio_close`.
- The system shall store diagnostics and return failed startup or unconfirmed cleanup for inspection without resubmitting or killing a saved numeric child identity through `studio_recovery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: studio_preflight
  Given an approved internal source bundle and installed fingerprint
  When `studio_preflight` encounters changed bytes or provider routing
  Then no child or foreign runtime starts
Scenario: studio_owned_start
  Given an isolated current local project
  When `studio_owned_start` starts or sees an existing retained attempt
  Then only the new admitted attempt starts and the retained attempt requires inspection
Scenario: studio_read
  Given an owned live child and current caller authority
  When `studio_read` receives actual compiled data, stale source, redirects or oversized output
  Then only the exact current compiled snapshot is returned
Scenario: studio_close
  Given a running owned Studio and private local runtime
  When `studio_close` stops the work
  Then the owned child exits and the exact private runtime reports stopped
Scenario: studio_recovery
  Given an interrupted startup or changed cleanup profile
  When `studio_recovery` runs
  Then diagnostics survive and foreign resources remain untouched
```

## SHOULD - Technical
Use the verified Node entrypoint with the explicit ipv4first DNS option observed
in the installed Studio probe. Upstream GET /__studio/session returns controls;
GET /__studio/document is the renderer document and must not be mistaken for the
inspector snapshot. Disable proxy inheritance and redirects. Preserve the real
typed snapshot internally, including all selected Companion fields. Its native
identifiers contain private absolute paths; the later broker must map them to
app-owned opaque identities and isolate preview resources before exposing them.

Keep a retained NEW/STARTING/READY/CLOSED/FAILED_CLEANED/NEEDS_INSPECTION state.
Never reconnect to or terminate a numeric PID from that file. Fresh authority is
checked before and after bounded observations. Cleanup does not need continuing
user authority to stop already owned work. Changed executable/profile bytes must
prevent cleanup commands from targeting unreviewed code or another data root.
Full app service, independent approval/standing scope, mutations, source history,
human controls, shared feedback/reuse, media portability and reporting remain
mandatory parent requirements, not implemented by this adapter.

The approved caller supplies the exact expected compiled file set and Author root;
the snapshot cannot declare its own acceptance set. Runtime storage is created or
inspected before preflight, each existing component rejects links/reparse points,
and stable directory identities are bound and rechecked before cleanup. The HTTP
deadline covers connect, headers and streamed body; an owned socket watchdog ends
inactivity-resistant streams and authority/log checks run between body chunks.
Private command phase records retain bounded output before temporary capture files
are deleted, including nonzero exit and interrupted/capture-failure diagnostics.

The Windows native backend assigns the suspended child to a kill-on-close Job
Object before resume. Continuous pipe drains enforce one retained-byte cap and
stop the owned tree on overflow even with no snapshot requests. Tree ownership
survives launcher exit; unsupported platforms reject before launching. Before
and after HTTP reads, inspect the exact loopback listener and require its live
process handle to belong to the retained job. Source equality alone does not
establish listener ownership. New runtime admission requires exclusive final
directory creation; existing storage is retained for inspection. Anchor project
paths absolutely without resolving away links before validation.

Preflight and shutdown use a separately opted-in synchronous owned command
runner. General agent capture keeps its existing stdin and daemon semantics.
Every command retains tree authority until confirmed teardown, including launch
rollback failure. Pending command or launch recovery prevents CLOSED and
FAILED_CLEANED. The live retry authority is never reconstructed from stored PIDs.

## Authorized parameters
STARTUP_SECONDS = 45
HTTP_SECONDS = 2
COMMAND_SECONDS = 120
MAX_RESPONSE_BYTES = 8388608
MAX_LOG_BYTES = 1048576
POLL_SECONDS = 0.25
MAX_DIAGNOSTIC_BYTES = 8388608
CHUNK_BYTES = 65536
