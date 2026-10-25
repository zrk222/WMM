# Spec: analytics-read-indexes
Status: implementation; hosted timing acceptance remains required

## MUST - Functional core
### Requirements (EARS)
- The system shall create `analytics_indexes` idempotently for app/source report history and project/time request budgets, preserving existing rows and constraints while allowing selected-scope history and rolling 86400 seconds quota queries to use SQLite indexes instead of whole-table scans.
- The system shall reject `analytics_quota` at the unchanged10 Clarity requests within 86400 seconds, counting failed attempts and rotations, while skipping the unused quota-count query for other providers and preserving their request-attempt records and expiry cleanup.
- The system shall store `analytics_history` with the unchanged100-report per-source cap and original source/version/hash bindings, preserving other apps and sources when history trimming executes under existing lease and commit guards.
- The system shall emit `analytics_proof` with actual SQLite query plans and scaled synthetic request/report fixtures, the unchanged105-refresh performance test below 10 seconds locally, existing connector/race regressions and hosted CI evidence when available, without raising the timeout or claiming production throughput from fixtures.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: analytics_indexes
  Given existing reports and request budget history
  When `analytics_indexes` initializes twice
  Then scoped history and quota lookups use their named indexes and retain existing rows
Scenario: analytics_quota
  Given current project request attempts
  When `analytics_quota` reserves Clarity or other provider reads
  Then Clarity retains its exact daily cap and other providers avoid an unused count
Scenario: analytics_history
  Given more than100 reports in one source and reports in another app
  When `analytics_history` trims the selected source
  Then exactly its latest100 reports remain without affecting other source records
Scenario: analytics_proof
  Given scaled isolated fixtures and existing connector tests
  When `analytics_proof` runs
  Then query plans timing and denial/recovery assertions are recorded without a provider call
```

## WON'T - Out of scope
No timeout increase, automatic test retry, skipped performance test, reduced105
refresh workload, journal durability change, shared transaction bypass, credential
cache or production speed claim. Hosted acceptance remains pending until measured.
