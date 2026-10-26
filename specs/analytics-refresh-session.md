# Spec: analytics-refresh-session
Status: implementation

## MUST - Functional core
### Requirements (EARS)
- The system shall store reservation and completion in separate durable guarded transactions on one refresh-scoped SQLite connection, closing that connection after success or failure and retaining the existing 15 seconds busy timeout and foreign-key enforcement, identified by `analytics_session_commits`.
- The system shall reject provider work until reservation has committed, execute provider reads without an active SQLite transaction and allow independent readers and writers during provider latency with no active SQLite transaction and the existing 15 seconds provider timeout, identified by `analytics_network_unlock`.
- The system shall reject stale or revoked authority at every transaction entry and commit, discard results after source rotation or disconnect and preserve failed read reservations and the Clarity cap of 10 attempts per rolling 86400 seconds, identified by `analytics_authority_rechecks`.
- The system shall emit baseline and candidate timing evidence for the unchanged 105 reads and latest 100 reports acceptance check with its existing 10 seconds limit, plus injected authority and commit failures without weakening SQLite durability, identified by `analytics_performance_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: analytics_session_commits
  Given an isolated analytics source and database
  When `analytics_session_commits` exercises its guarded refresh
  Then transaction boundaries and required outcomes are observed
Scenario: analytics_network_unlock
  Given an isolated analytics source and database
  When `analytics_network_unlock` exercises its guarded refresh
  Then transaction boundaries and required outcomes are observed
Scenario: analytics_authority_rechecks
  Given an isolated analytics source and database
  When `analytics_authority_rechecks` exercises its guarded refresh
  Then transaction boundaries and required outcomes are observed
Scenario: analytics_performance_proof
  Given an isolated analytics source and database
  When `analytics_performance_proof` exercises its guarded refresh
  Then transaction boundaries and required outcomes are observed
```

## WON'T - Out of scope
No global connection pool, persistent database handle, synchronous mode change, provider retry or timing-limit change. Hosted CI acceptance remains required.
