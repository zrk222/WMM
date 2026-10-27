# Spec: apple-analytics-parser
Parent: apple-analytics-metrics. This offline parser is a prerequisite only; live transport, durable reconciliation, scheduling, UI and provider acceptance remain required.

## MUST - Validate one complete App Downloads Standard instance
### Requirements (EARS)
- When `SEGMENT_INTEGRITY` reads a segment, the system shall reject mismatched declared bytes or MD5 before decompression and return no observations. [AP1]
- When `SEGMENT_BOUNDS` receives more than 50 segments, a segment above 16 MB compressed or an instance above 64 MB decompressed, the system shall reject the instance and return no observations. [AP2]
- When `REPORT_SCHEMA` reads a gzip CSV segment, the system shall validate required named columns independent of their order and reject duplicate or missing required names, malformed dates, invalid counts and foreign app identity. [AP3]
- When `DOWNLOAD_TYPES` reads rows, the system shall return distinct original download, redownload and update categories and return unknown types without counting them as original downloads. [AP4]
- When `INSTANCE_RECONCILE` receives multiple dated instances, the system shall select complete data from the newest processing date for each event date and never add older versions for that date. [AP5]
- When `INCOMPLETE_SOURCE` receives an empty, damaged or incomplete instance, the system shall reject that instance and preserve any previously accepted observations. [AP6]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Integrity
 Given SEGMENT_INTEGRITY receives bytes with an incorrect MD5 or size
 When SEGMENT_INTEGRITY verifies the compressed segment
 Then SEGMENT_INTEGRITY rejects the segment before parsing
Scenario: Resource limits
 Given SEGMENT_BOUNDS receives an instance exceeding its declared size limit
 When SEGMENT_BOUNDS validates the source
 Then SEGMENT_BOUNDS rejects the whole instance
Scenario: Schema and app identity
 Given REPORT_SCHEMA receives reordered columns or a foreign app row
 When REPORT_SCHEMA validates the CSV records
 Then REPORT_SCHEMA accepts reordered columns and rejects the foreign app
Scenario: Meaning of download types
 Given DOWNLOAD_TYPES receives first-time, redownload, update and unfamiliar types
 When DOWNLOAD_TYPES groups the records
 Then DOWNLOAD_TYPES preserves those categories without fabricating installs
Scenario: Corrections
 Given INSTANCE_RECONCILE receives complete records for one date from two processing dates
 When INSTANCE_RECONCILE selects the current observations
 Then INSTANCE_RECONCILE returns the newer complete date without adding the older values
Scenario: Failure does not replace evidence
 Given INCOMPLETE_SOURCE receives a damaged instance after an earlier complete instance
 When INCOMPLETE_SOURCE evaluates the damaged instance
 Then INCOMPLETE_SOURCE rejects it and leaves the earlier observations intact
```

Inputs are in-memory synthetic or already authorized report bytes; this module
does not perform network requests, database writes or provider mutations. It does
not infer metrics for missing dates. Complete source status must be explicit; an
unverified collection of segments cannot be called complete. Actual provider
format compatibility remains NOT_RUN until tested against an authorized report.

## Authorized parameters
MAX_SEGMENTS = 50
MAX_COMPRESSED = 16777216
MAX_DECOMPRESSED = 67108864
MAX_ROWS = 250000

Compressed bytes are bounded per segment; decompressed bytes and rows are bounded
per instance. Reject on any limit instead of treating a truncated report as complete.
