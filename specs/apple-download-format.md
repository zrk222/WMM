# Spec: apple-download-format

Offline parser correction only. Live collection and provider acceptance remain incomplete.

## MUST - Parse documented App Store downloads
### Requirements (EARS)
- When `TSV_REPORT` parses an Apple report, the system shall accept gzip-compressed tab-delimited records up to 16 MB per segment using named columns independent of column order. [DF1]
- When `DOWNLOAD_TYPES` parses a documented Auto-update or Restore row, the system shall return update or restore respectively and preserve its original label. [DF2]
- When `BAD_REPORT` parses missing or duplicate required columns, malformed counts, foreign app identifiers or malformed row shapes, the system shall reject the entire instance. [DF3]
- When `EMPTY_REPORT` parses a header-only instance, the system shall return no observations and shall not replace previously accepted dated observations. [DF4]
- When `REPORT_COMPAT` encounters an unsupported delimiter in a report up to 16 MB per segment, the system shall reject the report without guessing missing values or fabricating counts. [DF5]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Documented delimiter
 Given TSV_REPORT has a gzip-compressed tab-delimited report with reordered columns
 When TSV_REPORT validates the report
 Then TSV_REPORT returns app-scoped observations from named columns
Scenario: Documented categories
 Given DOWNLOAD_TYPES has Auto-update and Restore rows
 When DOWNLOAD_TYPES classifies both rows
 Then DOWNLOAD_TYPES returns update and restore and preserves their original labels
Scenario: Invalid report
 Given BAD_REPORT has duplicate columns or a foreign app identifier
 When BAD_REPORT validates all rows
 Then BAD_REPORT rejects the entire instance
Scenario: Empty source
 Given EMPTY_REPORT has a header-only instance without dated observations
 When EMPTY_REPORT validates the instance
 Then EMPTY_REPORT does not replace prior observations
Scenario: Unsupported input
 Given REPORT_COMPAT has a report with an unsupported delimiter
 When REPORT_COMPAT validates the columns
 Then REPORT_COMPAT rejects the report without inventing counts
```

The existing parser limits and integrity checks remain in force. Apple documents
tab-delimited compressed reports and its Auto-update and Restore glossary at
https://developer.apple.com/help/app-store-connect-analytics/overview/analytics-reports-api/
and https://developer.apple.com/documentation/analytics-reports/app-download.
Actual provider reports are unavailable and live format acceptance remains NOT_RUN.

## Authorized parameters
MAX_SEGMENTS = 50
MAX_COMPRESSED = 16777216
MAX_DECOMPRESSED = 67108864
MAX_ROWS = 250000
