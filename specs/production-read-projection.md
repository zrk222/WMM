# Spec: production-read-projection
Status: draft

## MUST - Functional core
### Description
Remove redundant capability history queries within a single production read.
Reuse loaded immutable versions without caching app or authority state.

### Requirements (EARS)
- The system shall query each production history table once per capability listing through `projection_reads`.
- The system shall return current assessments from the same versions returned in the listing through `projection_consistency`.
- The system shall return saved revisions on the next listing and reject missing apps through `projection_freshness`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: projection_reads
  Given a populated production workspace
  When `projection_reads` loads capabilities
  Then each capability history is selected once
Scenario: projection_consistency
  Given saved capability and requirement histories
  When `projection_consistency` evaluates sources
  Then assessment inputs equal the listed current versions
Scenario: projection_freshness
  Given changed rights or app setup
  When `projection_freshness` loads again
  Then the new state is observed and missing apps still reject
```
