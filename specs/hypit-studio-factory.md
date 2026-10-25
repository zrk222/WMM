# Spec: hypit-studio-factory
Status: draft

## MUST - Functional core
### Description
Implement hypit-public-sessions T2: derive an exact execution summary from an
app-owned approved Hypit source job and construct a fresh private project. Do not
start Studio, reuse a render job runtime, or accept user-selected native paths.
The caller still supplies protected authority and the durable startup reservation.

### Requirements (EARS)
- The system shall return an exact summary hash binding current app revision source job inputs generated source closure a font of at most 16777216 bytes and installed runtime identity without native startup through `factory_plan`.
- The system shall reject foreign jobs changed app revisions stale rights source changes and unrecognized frozen job inputs through `factory_source`.
- The system shall reject creation unless the exact PREPARED registry reservation matches current summary inputs through `factory_reservation`.
- The system shall create a new isolated session directory with exclusive fixed files and a fresh private runtime profile through `factory_isolation`.
- The system shall reject linked or reparse directories replaced font bytes changed installation or existing session folders through `factory_paths`.
- The system shall return an internal NEW StudioProcess with no native child and exact source hashes only after final source and installation checks through `factory_ready`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: factory_plan
  Given a current app-owned approved Hypit source job
  When `factory_plan` builds a summary
  Then exact source font and runtime hashes are bound and no child starts
Scenario: factory_source
  Given a foreign job changed manifest or stale source rights
  When `factory_source` validates the frozen job
  Then preparation rejects without a session folder
Scenario: factory_reservation
  Given a missing changed or non-PREPARED startup reservation
  When `factory_reservation` requests project creation
  Then no project is created
Scenario: factory_isolation
  Given a valid startup reservation and current source
  When `factory_isolation` prepares the project
  Then fixed source files live in a new session directory separate from job runtime
Scenario: factory_paths
  Given a linked path changed font installation or existing project
  When `factory_paths` checks before creation and finalization
  Then it rejects without adopting private runtime state
Scenario: factory_ready
  Given exact source bytes in a fresh private project
  When `factory_ready` finishes preparation
  Then the returned internal StudioProcess is NEW and has no child or origin
```

## Authorized parameters
MAX_FONT_BYTES = 16777216
MAX_PROJECT_BYTES = 20971520
READ_SECONDS = 2
COMMAND_SECONDS = 120
LIVE_SESSIONS_PER_APP = 2
LIVE_SESSIONS_PER_SERVICE = 4
STARTUP_SECONDS = 45
MUTATION_SECONDS = 20

## Scope
The summary exposes hashes, declared local effects, limits and source job identity,
not paths, raw source, origin, PID or credentials. Fixed authoring currently uses
the approved-brief source profile; selected-agent projects and complete editing
remain required parent work. Retain partially created folders for inspection after
failure; do not recursively delete or implicitly retry. A prepared NEW object is
not a launched Studio or proof of runtime readiness. Actual factory/native/client
integration must be proven separately before claiming shared public operation.

The public summary binds every generated file's exact bytes, including package.json
and runtime.json, plus copied font bytes, complete bundle size and all declared
execution deadlines. Enforce the total bundle bound before directory creation.
After staging, recheck exact reservation ID/version/PREPARED state/intent, current
app/source/rights, font bytes, installation fingerprint, directory identity and
all staged hashes. The manager must revalidate immediately before later launch;
neither PREPARED state nor a NEW factory object restores one-time launch authority.
