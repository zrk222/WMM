# Spec: agent-entrypoints
Status: draft

## MUST - Discoverable local agent setup
### Requirements (EARS)
- The system shall return an offline interpreter and optional dependency report through `setup_status`.
- The system shall reject noncanonical origins before emitting a grant-mode launch configuration through `origin_guard`.
- The system shall show usable CLI and MCP setup instructions in Agent access through `setup_frontdoor`.
- The system shall return setup output excluding credentials and server-contact claims through `setup_privacy`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: setup_status
  Given an interpreter without the optional MCP dependency
  When `setup_status` inspects the selected environment
  Then the report names the missing dependency without installing packages
Scenario: origin_guard
  Given a remote or redirected origin
  When `origin_guard` validates setup
  Then configuration output is rejected
Scenario: setup_frontdoor
  Given the Agent access page
  When `setup_frontdoor` renders
  Then exact CLI and MCP module commands and grant guidance are available
Scenario: setup_privacy
  Given a process with a private bearer token
  When `setup_privacy` emits setup output
  Then no token value or connected-server assertion is returned
```

## Authorized parameters
The subprocess-only test bound is 15 seconds; no production timeout changes.
timeout = 15
Existing grant quota fixtures remain unchanged; source drift checks compare
changed lines against the base commit.
