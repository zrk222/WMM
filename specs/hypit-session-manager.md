# Spec: hypit-session-manager
Status: draft

## MUST - Functional core
### Description
Join registry, isolated factory, owned Studio broker and protected request authority
in one long-lived internal manager. Public transports remain the next T4/T5 tasks
of hypit-public-sessions. No session object retains permission from an earlier call.

### Requirements (EARS)
- The system shall reject manager calls without exact current protected request authority through `manager_authority`.
- The system shall reserve immutable startup before preparation and start at most 1 native session per retry key through `manager_once`.
- The system shall reject callback action project or body changes and recheck current source rights during native observations through `manager_live`.
- The system shall return UNKNOWN for uncertain startup edit or close including retained unresolved retry results with a native edit deadline of 20 seconds through `manager_unknown`.
- The system shall store only owned outcome or cleanup evidence outside revoked request authority without granting launch edit or native adoption through `manager_finalization`.
- The system shall return retained session metadata after manager restart without adopting a saved PID through `manager_restart`.
- The system shall serialize each session while avoiding a manager-wide lock across native calls through `manager_serialization`.
- The system shall stop new admission coordinate in-flight calls and retain confirmed or unresolved cleanup receipts on shutdown through `manager_shutdown`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: manager_authority
  Given no trusted request or a changed app operation envelope
  When `manager_authority` admits a call
  Then it rejects before native work
Scenario: manager_once
  Given concurrent identical startup calls
  When `manager_once` reserves and starts
  Then one native start occurs and retries return retained state
Scenario: manager_live
  Given revoked authority or stale rights during native work
  When `manager_live` checks a callback
  Then native dispatch or confirmed result adoption is denied
Scenario: manager_unknown
  Given an unconfirmed native result or retained uncertain retry
  When `manager_unknown` returns through outer execution
  Then it raises typed uncertainty without another send or start
Scenario: manager_finalization
  Given revoked authority and failed cleanup or storage
  When `manager_finalization` records an already-owned outcome
  Then capacity stays reserved until actual cleanup and durable terminal receipt
Scenario: manager_restart
  Given a registry with no corresponding owned object
  When `manager_restart` reads session state
  Then it requires inspection and never adopts a stored PID
Scenario: manager_serialization
  Given concurrent calls for one session and unrelated sessions
  When `manager_serialization` runs
  Then the same session is serialized without a global native-call lock
Scenario: manager_shutdown
  Given active or in-flight owned sessions
  When `manager_shutdown` stops the service
  Then admission stops and owned cleanup leaves durable or explicitly unresolved receipts
```

## Internal finalizer
The manager may temporarily clear protected and standing execution contexts only
inside a fixed registry-outcome function for its captured reservation ID/revision.
It may record UNKNOWN, cleanup-required or CLOSED after actual owned cleanup.
ACTIVE is recorded only inside current protected admission. It cannot execute
caller callbacks, source writes or native
commands in this narrow persistence path. Keep failed finalizer receipts in memory
and retain durable nonterminal capacity. Public routes cannot invoke it directly.
Public reconciliation requires trustworthy stopped-resource inspection and remains
unfinished; missing live objects never release capacity. Internal shutdown can
close actual owned objects after revocation, but session IDs alone grant no right.
