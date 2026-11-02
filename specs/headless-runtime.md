# Spec: headless-runtime
Status: draft

## MUST - Functional core
### Description
Offer an explicit owner-hosted headless process using the existing per-user workspace, private loopback server and workers.

### Requirements (EARS)
- The system shall reject a second desktop or headless runtime for the same workspace through `workspace_exclusion`.
- When headless mode starts, the system shall bind only the fixed loopback port and reject an occupied port through `fixed_binding`.
- When headless mode runs, the system shall open the existing user data path without browser or graphical initialization through `headless_lifecycle`.
- If startup fails or the runtime stops, the system shall release its workspace lock and close owned workers through `cleanup`.
- The system shall preserve existing native credential scope and reject any credential migration or fallback through `credential_scope`.
- When the runtime is interrupted, the system shall retain durable job receipts and reject replay of uncertain provider mutations through `recovery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: workspace_exclusion
  Given one process holding a workspace lock
  When `workspace_exclusion` starts another process
  Then the second process exits before starting workers
Scenario: fixed_binding
  Given the preferred loopback port is occupied
  When `fixed_binding` starts headless mode
  Then startup fails without choosing another port
Scenario: headless_lifecycle
  Given a supported local user workspace
  When `headless_lifecycle` starts
  Then no browser or graphical controller is opened
Scenario: cleanup
  Given a failed startup or process shutdown
  When `cleanup` completes
  Then another process can acquire the same workspace lock
Scenario: credential_scope
  Given protected credentials on the existing user and database path
  When `credential_scope` starts headless mode
  Then no secrets are copied or replaced
Scenario: recovery
  Given an interrupted uncertain campaign mutation
  When `recovery` restarts the worker
  Then the saved intent remains and no automatic replay is performed
```

## SHOULD - Technical
- Use the existing per-user workspace path and operating-system lock; do not register startup.
- Headless mode remains bound to 127.0.0.1 and cannot expose a network listener.
- Remote host and real credential acceptance remain NOT_RUN.

## Authorized parameters
PORT = 8765
SHUTDOWN_TIMEOUT_SECONDS = 10

Lifecycle test and shutdown deadlines in seconds:
timeout = 10
timeout = 15
timeout = 30
