# Spec: hypit-durable-jobs
Status: draft

## MUST - Functional core
### Description
Connect the installed Hypit adapter to the WMM durable worker. Freeze an existing current short-video brief, keep a private retained project, save the actual build identity during execution, and expose immutable decoded results within the selected app. This is a dependency for the mandatory integrated UI, shared editing, CLI/MCP, portability and KPI work in UPG-07 through UPG-09.

### Requirements (EARS)
- The system shall queue one app-scoped Hypit job for an exact current brief and reject reused request keys with changed inputs through `queue_identity`.
- The system shall persist the private project identity before submitting a build and persist its returned build ID before observing completion through `durable_attempt`.
- The system shall reject automatic resubmission when a retained attempt exists and return an existing committed artifact without another render through `restart_boundary`.
- The system shall reject changed frozen brief proof or lost running attempt ownership before storing immutable artifact bytes and their checksum through `atomic_artifact`.
- The system shall expose only selected-app artifact identifiers and reject missing or modified video bytes through `artifact_scope`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: queue_identity
  Given a current brief and a retry key
  When `queue_identity` is repeated
  Then the original job is returned and changed inputs are rejected
Scenario: durable_attempt
  Given an owned running job
  When `durable_attempt` submits local work
  Then the private project and actual build identity survive reopening the database
Scenario: restart_boundary
  Given a retained unfinished attempt
  When `restart_boundary` runs after worker recovery
  Then no second submission occurs and inspection is required
Scenario: atomic_artifact
  Given a render whose brief proof or job ownership changed
  When `atomic_artifact` is committed
  Then no accepted artifact row or shared output is created
Scenario: artifact_scope
  Given a saved decoded video
  When `artifact_scope` is checked from another app or after byte modification
  Then the artifact is rejected
```

## SHOULD - Technical
- Use the existing jobs table, idempotency keys, worker ownership and heartbeat. Use a separate Hypit attempt/artifact table; preserve the native silent-video portability contract.
- Generate declarative scenes from the frozen brief's exact script text. Split duration across its beats without deleting text or inventing claims. Validate with the existing authoring bounds before enqueue.
- Project directories live beneath the local store's Hypit directory and use app/job UUID identity selected by the application. Payloads cannot choose filesystem paths, executables or commands.
- Store runtime errors as closed workflow diagnostics. Retain failed private projects for inspection. A worker restart never equates a lost response with a failed submission.
- Keep artifact checksum validation, current proof status and human visual approval separate. No publication or paid generation is performed.

## Verification
Focused tests must use real isolated SQLite and the actual worker with a controlled adapter. Prove frozen input validation, idempotency conflicts, reopened attempt/build storage, replay without a second render, cancellation/staleness rejection, database failure cleanup and app/byte scope. The installed runtime has a separately retained actual render/decode receipt. Run full regression with unchanged candidate hashes, source mutation challenges, CF strict/architecture/QA and workflow evidence audit before scoped completion.
