# Spec: native-timeout-diagnostics
Status: draft

## MUST - Functional core
### Description
Prove retained process diagnostics after a real timeout without assuming Python
starts and emits both streams within the one-second execution window. Production
process deadlines, ownership and diagnostics are unchanged.

### Requirements (EARS)
- The system shall reject missing stdout or stderr markers after 5 seconds of readiness before exercising the actual timeout of 1 seconds through `diagnostic_readiness`.
- The system shall return the interrupted flag and both output streams after owned child cleanup through `diagnostic_retention`.
- The system shall return exactly 1 interrupted diagnostic record with no return code after executable creation fails through `diagnostic_creation`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: diagnostic_readiness
  Given a real child with startup deliberately delayed beyond the execution timeout
  When `diagnostic_readiness` observes both output streams
  Then the original wait function still enforces its one-second timeout
Scenario: diagnostic_retention
  Given an owned child that has emitted output before sleeping
  When `diagnostic_retention` observes the real timeout
  Then the interrupted diagnostics retain both markers after temporary cleanup
Scenario: diagnostic_creation
  Given an executable that does not exist
  When `diagnostic_creation` attempts process creation
  Then exactly one interrupted diagnostic record has no return code
```

## Authorized parameters
READINESS_SECONDS = 5
EXECUTION_SECONDS = 1
STARTUP_DELAY_SECONDS = 1.2
