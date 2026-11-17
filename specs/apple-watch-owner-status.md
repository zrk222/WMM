# Spec: apple-watch-owner-status
Status: draft

## MUST - Functional core
### Description
Report a valid scheduled Apple availability check in Watch the Work and saved reports.

### Requirements (EARS)
- When a saved current-source availability check has no report files, the system shall return a waiting observation and its next due time through `availability_waiting`.
- When a saved current-source availability check lists a complete daily App Downloads Detailed file, the system shall return a single Apple Analytics action without reporting a download count through `availability_action`.
- If the saved check is foreign, stale, or malformed, the system shall reject a file-available action through `availability_source`.
- When a saved availability result lists only other reports or needs initial Apple setup, the system shall return its distinct status through `availability_other`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: availability_waiting
  Given the current scheduled inventory has no files
  When `availability_waiting` projects the latest saved read
  Then the saved report says waiting and the next schedule date remains visible
Scenario: availability_action
  Given a saved complete daily Detailed file entry
  When `availability_action` renders Watch the Work
  Then it offers one Apple Analytics action without publishing or reporting downloads
Scenario: availability_source
  Given a foreign, stale, or malformed scheduled inventory
  When `availability_source` checks the bound result
  Then it does not offer a file-available action
Scenario: availability_other
  Given inventory with standard files only or no active Apple report stream
  When `availability_other` projects the saved check
  Then it distinguishes generic files from initial reporting setup
```

## SHOULD - Technical
- Keep existing checked numeric and waiting results unchanged.
- Use one exact saved read and the existing repair route; expose no private identifiers.
