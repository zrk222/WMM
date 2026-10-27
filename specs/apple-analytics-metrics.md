# Spec: apple-analytics-metrics
Status: implementation pending; native provider readback and full product acceptance are NOT_RUN.

## MUST - App-scoped analytics observations
### Requirements (EARS)
- When `AM_SCOPE` refreshes an authorized app connection, the system shall return only results from that app's verified report requests, reports, instances and typed segments. [AM1]
- When `AM_TRANSPORT` receives an unsafe segment destination, redirect, malformed metadata, a response above 16 MB compressed or mismatched byte size or MD5 checksum, or a segment request exceeds `timeout=15`, the system shall reject the segment without disclosing its signed URL or credentials. Before downloading bytes, it shall require a complete inventory of at most 50 segments and a total advertised size no greater than 64 MiB. [AM2]
- When `AM_SCHEMA` parses a supported standard report, the system shall validate its schema, report identity, app identity, dates, dimensions and counts before retaining observed metrics with source provenance. [AM3]
- When `AM_DOWNLOADS` reads download data, the system shall distinguish first-time downloads, redownloads and updates and shall not equate downloads with installs or revenue. [AM4]
- When `AM_UNKNOWN` encounters an unknown, suppressed, unavailable, stale, partial or malformed report, the system shall return that state without substituting zero or implying complete coverage. [AM5]
- When `AM_RECONCILE` sees repeated segments, late data or corrections, the system shall preserve source identities and replace each affected report date with the complete set from the newest processing date without double counting across retries and restarts. [AM6]
- When `AM_SCHEDULE` refreshes supported app reports on a user-configured schedule, the system shall store failure, last success, coverage and recovery information through the existing durable worker. [AM7]
- When an owner or admitted agent inspects `AM_SURFACE`, the system shall return supported observations with observation times, coverage and data caveats through the existing interface and authorized operation surfaces. [AM8]
- When `AM_PRIVACY` stores or exports a result, the system shall exclude provider credentials, signed download URLs and unrelated apps, and shall not perform provider writes. [AM9]

## Authorized parameters
timeout = 15
MAX_PARTITIONS_PER_APP = 1000
MAX_PARTITION_BYTES = 4194304
MAX_APP_BYTES = 16777216
max_workers = 2

The partition and app byte budgets are local serialized-storage limits, not
Apple provider limits. `max_workers` is used only by the SQLite offline
concurrency test; it is not a runtime setting.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Verified scoped metrics
 Given AM_SCOPE has an authorized connection and a ready report instance
 When AM_SCOPE downloads and verifies every supported segment
 Then AM_SCOPE records app-scoped observations with source and coverage
Scenario: Hostile or damaged segment
 Given AM_TRANSPORT receives a foreign destination or altered segment bytes
 When AM_TRANSPORT validates the segment
 Then AM_TRANSPORT rejects the response without leaking credentials
Scenario: Report schema and identity
 Given AM_SCHEMA has a report with an invalid field or foreign app identity
 When AM_SCHEMA parses the report
 Then AM_SCHEMA rejects the data before retaining observations
Scenario: Download event meaning
 Given AM_DOWNLOADS has first-time downloads, redownloads and updates
 When AM_DOWNLOADS reports the observed totals
 Then AM_DOWNLOADS keeps those categories distinct from installs and revenue
Scenario: Unavailable data
 Given AM_UNKNOWN has no usable report or only partial coverage
 When AM_UNKNOWN presents the result
 Then AM_UNKNOWN reports unknown or partial rather than a fabricated zero
Scenario: Corrections and retries
 Given AM_RECONCILE has previously observed a report segment
 When AM_RECONCILE refreshes after a retry or provider correction
 Then AM_RECONCILE preserves provenance and avoids duplicate counts
Scenario: Scheduled recovery
 Given AM_SCHEDULE has a configured refresh and its provider read fails
 When AM_SCHEDULE resumes after restart
 Then AM_SCHEDULE retains failure and last success while retrying within its schedule
Scenario: Owner and agent readback
 Given AM_SURFACE has a supported report and an admitted agent
 When AM_SURFACE displays the observed metrics
 Then AM_SURFACE returns the observations, times and coverage caveats
Scenario: Private source information
 Given AM_PRIVACY has private source information and app-scoped observations
 When AM_PRIVACY stores or exports the result
 Then AM_PRIVACY excludes private source information and foreign app data
```

## Scope and boundaries
The existing readiness inventory is the entry point. This packet must cover the
five declared standard report families and explain metric availability separately;
an initial download-family implementation does not complete the feature. Actual
provider report instances, scheduling, UI, CLI/MCP and acceptance remain required.
Private account identifiers, raw reports, credentials and signed URLs stay out of Git.
No autonomous external write, spend, publication or provider access grant is added.

Apple's [report download documentation](https://developer.apple.com/documentation/appstoreconnectapi/downloading-analytics-reports)
describes report instances, segments, byte size and checksums; its [segment endpoint](https://developer.apple.com/documentation/appstoreconnectapi/get-v1-analyticsreportinstances-_id_-segments)
states that download links expire after five minutes. Its [downloads report](https://developer.apple.com/documentation/analytics-reports/app-download)
distinguishes download types and allows late data and corrections. Apple identifies
the checksum as [MD5](https://developer.apple.com/documentation/appstoreconnectapi/analyticsreportsegment/attributes-data.dictionary)
and documents that newer processing dates replace older records for the same report
date in its [correction guidance](https://developer.apple.com/documentation/analytics-reports/data-completeness-corrections).
Only a complete instance may replace an earlier complete date; retain prior data and
mark the newer instance partial if a segment fails. Column names, not positions,
must identify fields. Final transport host policy and actual permitted response
formats require verification before enabling live reads.
