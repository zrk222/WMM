# Spec: hypit-session-registry
Status: draft

## MUST - Functional core
### Description
Implement the durable storage portion of hypit-public-sessions T1. Internal
registry methods do not grant caller approval, native ownership or stopped-resource
proof. The manager and inspector must supply those separately before transitions.

### Requirements (EARS)
- The system shall store one immutable startup intent per app and request key before returning launch permission through `registry_once`.
- The system shall reject changed retry inputs and return matching retained state with launch permission false through `registry_retry`.
- The system shall reject new reservations above 2 nonterminal sessions per app or 4 nonterminal sessions per datastore through `registry_capacity`.
- The system shall reject stale revisions illegal state transitions malformed saved rows or broken history links through `registry_integrity`.
- The system shall return retained nonterminal sessions after restart without PID endpoint path or launch authority through `registry_restart`.
- The system shall store UNKNOWN or cleanup-required outcomes while retaining capacity and release capacity only on an internal confirmed CLOSED transition through `registry_recovery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: registry_once
  Given concurrent reservations with identical startup input
  When `registry_once` reserves startup
  Then exactly one caller receives launch permission
Scenario: registry_retry
  Given a retained reservation
  When `registry_retry` receives matching or changed input
  Then matching input cannot launch again and changed input rejects
Scenario: registry_capacity
  Given retained unresolved sessions across reopened stores
  When `registry_capacity` reserves another startup
  Then app and datastore ceilings remain enforced
Scenario: registry_integrity
  Given stale revisions tampered rows or skipped transition history
  When `registry_integrity` reads or changes state
  Then it rejects without changing retained state
Scenario: registry_restart
  Given a reopened registry with unresolved reservations
  When `registry_restart` lists selected-app metadata
  Then inspection is required and native authority is never restored
Scenario: registry_recovery
  Given an unresolved startup or cleanup
  When `registry_recovery` records an internal outcome
  Then nonterminal states retain capacity and confirmed CLOSED releases it
```

## Authorized parameters
MAX_APP_ACTIVE = 2
MAX_STORE_ACTIVE = 4
MAX_APP_HISTORY = 100
MAX_TRANSITIONS = 50

## Internal boundary
The reservation stores app version/hash, source job ID/hash, execution summary
hash and installation ID, plus a server-generated opaque session ID. No paths,
URLs, raw source, PIDs, credentials or arbitrary error text belongs in it.
Transitions are PREPARED -> ACTIVE/UNKNOWN/CLEANUP_REQUIRED/CLOSED;
ACTIVE -> CLOSING/UNKNOWN/CLEANUP_REQUIRED/CLOSED;
CLOSING -> UNKNOWN/CLEANUP_REQUIRED/CLOSED;
UNKNOWN -> CLEANUP_REQUIRED/CLOSED;
CLEANUP_REQUIRED -> CLEANUP_REQUIRED/CLOSED. CLOSED is terminal.
Every transition appends previous hash, revision, fixed outcome code and timestamp.
The full row checksum binds identity, immutable input and complete history.
This detects uncoordinated corruption, not malicious coordinated database rollback.
No public finalization or reconciliation route is implemented here. CLOSED requires
a trusted manager's actual owned cleanup proof or future restart inspector proof;
the registry validates a closed proof shape, not real native resource liveness.
