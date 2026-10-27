# Spec: apple-reconcile-order

This scope covers offline App Downloads Standard reconciliation only. Persistent
report partitions, source enumeration and live provider acceptance remain separate.

## MUST - Reconcile reordered source segments
### Requirements (EARS)
- When `EQUIVALENT_SEGMENTS` receives complete instances with the same processing date and identical rows in a different order, the system shall accept both without duplicating their observations. [RO1]
- When `DIFFERENT_COUNTS` receives instances with the same processing date but different counts or row multiplicities, the system shall reject the conflict without selecting either instance. [RO2]
- When `DIFFERENT_PROVENANCE` receives equal-date instances with different source segment identities or source hashes, the system shall reject the conflict without claiming equivalence. [RO3]
- When `NEWER_DATA` receives complete instances with different processing dates, the system shall retain the newest complete observation set for each affected report date. [RO4]
- When `CROSS_APP` receives complete instances from different apps, the system shall reject the combined input. [RO5]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Identical segments in reverse order
 Given EQUIVALENT_SEGMENTS has two complete instances with reversed rows
 When EQUIVALENT_SEGMENTS reconciles them
 Then EQUIVALENT_SEGMENTS returns one observation set
Scenario: Conflicting rows
 Given DIFFERENT_COUNTS has equal-date instances with different row multiplicities
 When DIFFERENT_COUNTS reconciles them
 Then DIFFERENT_COUNTS rejects the conflict
Scenario: Different source identities
 Given DIFFERENT_PROVENANCE has equal-date rows with different source identities
 When DIFFERENT_PROVENANCE reconciles them
 Then DIFFERENT_PROVENANCE rejects the conflict
Scenario: Later correction
 Given NEWER_DATA has complete instances with distinct processing dates
 When NEWER_DATA reconciles them
 Then NEWER_DATA retains the newest complete data for each affected date
Scenario: Cross-app denial
 Given CROSS_APP has two instances from different apps
 When CROSS_APP reconciles them
 Then CROSS_APP rejects the combined input
```

## Authorized parameters
MAX_SEGMENTS = 50
MAX_COMPRESSED = 16777216
MAX_DECOMPRESSED = 67108864
MAX_ROWS = 250000

This does not infer that differently segmented data is equivalent. Empty reports
have no dated observations and cannot clear prior data. Live scheduling and
per-report/granularity database partitioning remain unimplemented.
