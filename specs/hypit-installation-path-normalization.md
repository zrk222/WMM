# Spec: hypit-installation-path-normalization
Status: test-only CI repair; runtime discovery remains unchanged.

## MUST - Canonical identity assertion

### Description
The npm discovery test must compare the canonical resolved entrypoint path
passed by `discover()` with the canonical expected path. On Windows, when the
temporary directory has a native 8.3 alias, the test must exercise discovery
through that alias and still assert the canonical result. Every discovery path
must continue to prove Hypit is not executed.

### Requirements (EARS)
- The system shall return an npm entrypoint whose resolved path equals the
  resolved expected path constructed by the test.
- When a native Windows 8.3 alias is available, the system shall return the canonical npm entrypoint for discovery from the native Windows 8.3 path.
- The system shall return direct and npm-wrapper discovery results without
  invoking `mission_control.hypit_installation.capture`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: npm discovery from canonical and short Windows paths
  Given an isolated npm wrapper and a Node path
  And a native 8.3 alias when the host exposes one
  When installation discovery fingerprints the npm entrypoint
  Then the expected and observed paths are compared after resolution
  And Hypit is not executed
```

