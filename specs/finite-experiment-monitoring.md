# Spec: finite-experiment-monitoring
Status: approved

## MUST - Functional core
### Description
A current verified app owner may configure a finite local analysis schedule for an existing observed experiment. This capability authorizes local evidence assessment only.

### Requirements (EARS)
- When the current app owner enables monitoring, the system shall bind `owner_binding` to the exact owner role version, app version, experiment hash, expiry and observation ceiling.
- The system shall accept `finite_limits` of 1 through 30 observations, 1 through 168 hours cadence, and an expiry no more than 90 days after authorization.
- When an eligible schedule is due, the system shall store `atomic_reservation` for one observation and one deduplicated job in the same database transaction.
- If owner role, app version, experiment hash, schedule version, expiry or OFF state changes, the system shall reject `current_admission` before assessment commits.
- When a job succeeds, fails, is interrupted or resumes, the system shall preserve `bounded_recovery` without spending more than the reserved observation ceiling.
- The system shall expose `owner_summary` with remaining observations, expiry, latest job state and local-only scope without authorizing publication, provider writes or spending.
- When an old schedule or restored snapshot lacks finite owner authority, the system shall reject `legacy_pause` admissions until a fresh owner authorization.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: owner_binding
  Given an observed experiment and a verified current owner
  When `owner_binding` saves monitoring
  Then it retains the exact owner role version and experiment hash
Scenario: finite_limits
  Given an owner configuration
  When `finite_limits` checks the requested cadence, expiry and ceiling
  Then 0 observations or an expiry beyond 90 days is rejected
Scenario: atomic_reservation
  Given one due observation and two scheduler invocations
  When `atomic_reservation` claims it
  Then one job and one reservation are retained
Scenario: current_admission
  Given a queued observation whose owner or app changed
  When `current_admission` checks the assessment transaction
  Then no assessment is committed
Scenario: bounded_recovery
  Given an interrupted or failed observation
  When `bounded_recovery` reconciles it
  Then reserved observations are not reused beyond the ceiling
Scenario: owner_summary
  Given an owner reviewing a schedule
  When `owner_summary` presents monitoring
  Then it shows expiry and remaining observations without external-effect authority
Scenario: legacy_pause
  Given a previously enabled or restored schedule without finite authority
  When `legacy_pause` evaluates it
  Then it is disabled until a fresh owner authorization
```

## SHOULD - Technical
- Reuse existing experiment evaluation and worker lease mechanisms; do not call a provider.
- Use the same embedded Python engine on iOS and describe foreground-only execution honestly.
- Expose zero observations as exhausted, never as successful measurement or conversion.

## Authorized parameters
MAX_OBSERVATIONS = 30
MAX_EXPIRY_DAYS = 90
MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 168
DEFAULT_OBSERVATIONS = 7
DEFAULT_EXPIRY_DAYS = 7

The following values are isolated test-fixture samples, not additional product defaults or runtime limits. The observation samples exercise the authorized 1–30 range; the worker count and timeout apply only to the local concurrency and HTTP test harness.

max_observations = 1
max_observations = 2
max_observations = 30
max_workers = 2
timeout = 10
