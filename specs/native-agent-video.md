# Spec: native-agent-video
Status: draft

## MUST - Functional core
### Description
Operate the existing validated app-screen renderer through shared agent interfaces
and standing approval. Preserve exact source proof and actual decoded artifacts.

### Requirements (EARS)
- The system shall return native render history and queue an exact current brief through fixed shared operations through `native_parity`.
  Native execution shall record actual proof-checking, screen-copy, encoding and artifact-commit steps in the existing live monitor.
- The system shall bind current native executable and font hashes into a selected native workflow summary and reject unavailable or changed runtime access through `native_readiness`.
- The system shall carry standing authority into native queued jobs and reject revoked or changed proof before an artifact commit through `native_scope`.
- The system shall return the same saved native render job through idempotent CLI and MCP requests while rejecting foreign or ungranted input through `native_clients`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: native_parity
  Given a current approved native video brief
  When `native_parity` queues and reads history
  Then the existing renderer service and actual saved artifact are used
Scenario: native_readiness
  Given a missing or changed native tool
  When `native_readiness` checks selected scope
  Then activation or admission is rejected with a repair requirement
Scenario: native_scope
  Given a standing-owned native job
  When `native_scope` is revoked before commit
  Then no accepted artifact is committed
Scenario: native_clients
  Given a repeated native queue request and foreign app request
  When `native_clients` call the fixed operations
  Then the repeated request returns the saved job and the foreign request is rejected
```

## SHOULD - Technical
- Reuse Renders.queue/list and existing media validation; no generic job bypass.
  Shared operations are native.read and native.queue. Native source/rights proof
  remains validated on every queue and commit, independent of standing approval.
- Native runtime inventory uses fixed existing FFmpeg/FFprobe/font detection and
  file SHA256 values, with public hashes only. No subprocess or provider is called
  to inspect runtime identity. Unavailable files are explicit setup requirements.
- Existing native output is silent H.264 with app screens and Latin captions.
  Rich media, full editing and selected-agent authoring remain required parent
  capabilities, not delivered by transport parity. Do not claim universal language.

## Authorized parameters
timeout = 30
Existing monitor bounds are preserved:
MAX_JOBS = 100
MAX_EVENTS = 200
