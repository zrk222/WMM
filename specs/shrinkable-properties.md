# Spec: shrinkable-properties
Status: approved

## MUST - Functional core
### Description
Use shrinkable generated parser inputs without changing production behavior.
### Requirements (EARS)
- The system shall emit minimized failing examples for media ranges, canonical JSON, grant tokens and consent expiry under `shrinking`.
- The system shall store named negative assertions independently of synthetic examples under `regressions`.
- The system shall reject dependencies that do not match declared wheel hashes under `pinned_dependencies`.
- The system shall store synthetic examples in an isolated replay database under `example_replay`.
- The system shall emit property-test results and replay data from the declared CI core profile under `ci_profile`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: shrinking
 Given synthetic parser fixtures
 When `shrinking` executes
 Then the declared property and replay boundary are verified
Scenario: regressions
 Given synthetic parser fixtures
 When `regressions` executes
 Then the declared property and replay boundary are verified
Scenario: pinned_dependencies
 Given synthetic parser fixtures
 When `pinned_dependencies` executes
 Then the declared property and replay boundary are verified
Scenario: example_replay
 Given synthetic parser fixtures
 When `example_replay` executes
 Then the declared property and replay boundary are verified
Scenario: ci_profile
 Given synthetic parser fixtures
 When `ci_profile` executes
 Then the declared property and replay boundary are verified
```

## SHOULD - Technical
Hypothesis profiles run reuse, generate and shrink. Every discovered bug receives a permanent named regression in the fix PR. Cache trust scopes separate PRs from main and shards from each other. No generated input is an operational credential.
