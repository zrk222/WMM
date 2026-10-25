# Spec: ci-agent-profile
Status: implementation

## MUST - Functional core
### Description
Make CI exercise the optional MCP adapter and all existing browser logic suites.
The native installed Hypit profile remains separate from hosted CI prerequisites.

### Requirements (EARS)
- The system shall return a failing exit code unless docs/requirements-mcp.txt is installed and mcp version is 1.30.0 before Python regression through `ci_mcp_profile`.
- The system shall run every tests/*.test.cjs and tests/*.test.mjs file of formats cjs and mjs through `ci_browser_profile` before Python regression, retaining the existing Windows runner, native-tool prerequisite, privacy check and full Python discovery.
- The system shall assign the complete discovered Python suite to four deterministic workers through `ci_shards`, preserving each discovered test instance exactly once and emitting the same full inventory hash with per-worker counts.
- The system shall return individual verbose test outcomes within a 45-minute limit per worker through `ci_budget`, retain failure status and run remaining workers after another worker fails.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: ci_mcp_profile
  Given the hosted Windows runner
  When `ci_mcp_profile` prepares the selected Python
  Then the declared optional MCP dependency is installed and its version checked
Scenario: ci_browser_profile
  Given existing browser logic suites
  When `ci_browser_profile` selects tests
  Then all matching files run and a failure stops CI
Scenario: ci_shards
  Given the complete discovered Python suite
  When `ci_shards` plans workers
  Then the union preserves every test instance exactly once
Scenario: ci_budget
  Given a slow hosted runner
  When `ci_budget` executes the selected tests
  Then individual outcomes are printed and failures remain failures
```

## WON'T - Out of scope
Local command/config checks do not prove GitHub execution. Retain the actual
remote run result separately. Do not report hosted Hypit installation coverage
or zero skips unless the exact runtime result proves it.
