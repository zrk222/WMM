# Spec: apple-metrics-foundation

Local foundation for the existing Apple analytics goal. This milestone does not
enable a live segment download, prove provider acceptance or complete the other
four requested Apple report families. Preserve the manual import fallback.

## MUST - Durable, app-scoped Apple observations
### Requirements (EARS)
- When `PARTITION` stores validated downloads, the system shall partition records by app, connection identity and version, report identity, report family, granularity and event date. [MF1]
- When `RECONCILE` receives a complete newer processing date for a partition, the system shall store the new partition atomically with source provenance and without summing older values. [MF2]
- When `CONFLICT` receives a different observation multiset for the same partition and processing date, the system shall reject the new result and preserve the current partition. [MF3]
- When `STALE_ATTEMPT` loses its job lease, job attempt, app version, connection version, schedule version, active schedule or required authority, the system shall reject all observation writes in the same transaction. [MF4]
- When `TRANSPORT` attempts live segment retrieval without a reviewed exact host policy, the system shall return TRANSPORT_DISABLED before credential lookup, DNS or socket use. [MF5]
- When `SCHEDULE` is created or restored, the system shall store a paused state until an authorized owner enables a versioned cadence between 1 hour and 7 days. [MF6]
- When `DISPATCH` schedules a due read, the system shall create at most 1 outstanding job per schedule and atomically advance its due time. [MF7]
- When `FAILED_READ` records a disabled, waiting, empty, partial or failed refresh, the system shall preserve prior observations and last successful ingestion time. [MF8]
- When `PRIVACY` records results or errors, the system shall exclude credentials, signed URLs and raw provider exception text from jobs, audit, exports and saved observations. [MF9]
- When `RECOVERY` resumes after interruption, the system shall reject cross-app or duplicate writes and exclude credentials and active scheduling authority from snapshots. [MF10]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Separate partitions
 Given PARTITION has app and report identities
 When PARTITION stores observations for distinct sources or granularities
 Then PARTITION keeps their records isolated
Scenario: Newer processing date
 Given RECONCILE has an older complete observation set
 When RECONCILE commits a newer complete set for the same date
 Then RECONCILE replaces the older set atomically
Scenario: Conflicting same-date input
 Given CONFLICT has a current complete partition
 When CONFLICT receives different rows for the same processing date
 Then CONFLICT preserves the current partition
Scenario: Stale job
 Given STALE_ATTEMPT has an expired lease or changed authority
 When STALE_ATTEMPT tries to commit observations
 Then STALE_ATTEMPT writes no observations
Scenario: Disabled transport
 Given TRANSPORT has no reviewed exact production host
 When TRANSPORT requests a live segment
 Then TRANSPORT returns TRANSPORT_DISABLED before credentials or network access
Scenario: Initial pause
 Given SCHEDULE is newly created or restored
 When SCHEDULE is read before owner enablement
 Then SCHEDULE remains paused
Scenario: Bounded dispatch
 Given DISPATCH has a due enabled schedule
 When DISPATCH runs concurrently
 Then DISPATCH creates at most one outstanding job
Scenario: Failed refresh
 Given FAILED_READ has previously recorded observations
 When FAILED_READ encounters a partial or disabled refresh
 Then FAILED_READ retains previous observations and their timestamps
Scenario: Safe diagnostic
 Given PRIVACY encounters a provider exception
 When PRIVACY writes an error or export
 Then PRIVACY omits credentials signed URLs and raw exception text
Scenario: Restart
 Given RECOVERY has an interrupted job or restored snapshot
 When RECOVERY resumes
 Then RECOVERY preserves isolation without restoring active authority
```

No claimant can derive zero for an absent date or infer a real install, revenue,
retention or causal lift from synthetic inputs. Source freshness, transport
completeness and Apple event-data finality are distinct fields. Missing or
unverified production host evidence cannot be bypassed through configuration.

## Authorized parameters
MAX_DIMENSION_TEXT = 200
MAX_PARTITIONS_PER_APP = 1000
MAX_PARTITION_BYTES = 4194304
MAX_APP_BYTES = 16777216
timeout = 15
max_workers = 2
