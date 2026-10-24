# Spec: hypit-owned-runtime
Status: draft

## MUST - Functional core
### Description
Integrate installed local Hypit execution with the existing WMM owned execution boundary. Render only the validated declarative project, retain build identity and decoded MP4 output, and stop the private runtime after work. This packet is the runtime dependency for durable WMM jobs, not the finished UI or selected-agent authoring workflow.

### Requirements (EARS)
- The system shall detect the installed Hypit launcher and return a hash-bound runtime identity without installing software or connecting accounts through `runtime_identity`.
- The system shall stage exactly the validated five project files and selected local font in an owned empty directory and reject an existing populated directory through `private_project`.
- The system shall validate the installed compiler and selected graph before build submission and reject any selected endpoint other than html.local and media.local through `local_graph`.
- The system shall return the actual submitted build ID, inspect completion and export final.video before decoded media acceptance through `actual_build`.
- The system shall invoke fixed CLI commands through the existing restricted-environment runner with at most 180 seconds per command and store closed failure diagnostics without raw account data through `owned_execution`.
- The system shall abort a known unfinished build and stop its private runtime on cancellation or failure, while storing project history for inspection rather than silently restarting uncertain work through `runtime_cleanup`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: runtime_identity
  Given the installed launcher
  When `runtime_identity` is inspected
  Then executable bytes are hashed and a missing launcher produces a setup requirement
Scenario: private_project
  Given validated declarative source
  When `private_project` is staged
  Then only fixed source files and the local font are written into an owned empty directory
Scenario: local_graph
  Given a compiler plan containing an unexpected endpoint
  When `local_graph` is checked
  Then no build command is submitted
Scenario: actual_build
  Given an accepted local graph
  When `actual_build` runs
  Then a real build ID and exported decoded MP4 are returned
Scenario: owned_execution
  Given a cancellation callback and failing command
  When `owned_execution` is exercised
  Then the owned command stops and raw diagnostic data is excluded
Scenario: runtime_cleanup
  Given a submitted build and later cancellation
  When `runtime_cleanup` runs
  Then the known build is cancelled and private runtime shutdown is observed
```

## SHOULD - Technical
- The caller supplies an exclusive job-owned directory and heartbeat callback. User payloads never select executable, package root, output filename, command, runtime endpoints or font path.
- Preserve accepted build history for inspection. A command observation timeout does not establish terminal state; inspect the same build identity and do not resubmit.
- A cancelled build may already have completed; inspect actual status before reporting whether it was stopped. Cleanup failures remain explicit and do not produce success receipts.
- Verify real installed Hypit execution with a synthetic fixture separately from transport tests. No media-generation API, account inference, provider mutation or publication is authorized.

## Authorized parameters
COMMAND_TIMEOUT = 180
FOLLOW_WAIT_MS = 45000
POLL_SECONDS = 1
BUILD_TIMEOUT = 150
