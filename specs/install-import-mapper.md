# Spec: install-import-mapper

Status: draft

## MUST - Functional core
### Description
Turn an MMP CSV or JSON install export into a validated WMM install-attribution
batch and a human-readable coverage checklist. The mapper never writes to the
store, never invents missing values and never emits a batch it could not validate.

### Requirements (EARS)
- The system shall read a bounded CSV with headers or a JSON list of objects through `load_export`.
- The system shall require a mapping with nonempty `install_id`, `state` and `occurred_at` columns and an optional closed `state_values` map through `column_map`.
- The system shall emit only the exact batch shape accepted by `validate_batch`, and shall revalidate the result before returning `READY`.
- The system shall report `status`, rows read/emitted, counts per state, missing-value rejections, duplicate and conflicting install identities, unmapped columns, request identity and source-receipt hash through `coverage_checklist`.
- The system shall block on missing required values, unknown states, invalid timestamps, conflicting duplicates and an empty import.
- The system shall warn when coverage is incomplete or when the source-receipt hash was derived from the input rows rather than an original receipt.
- The system shall expose a CLI that writes the batch and optional checklist and exits nonzero when blocked.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: import_ready
  Given a CSV with mapped install columns and valid values
  When the mapper runs
  Then a validated batch and READY checklist are written
  And the owner service accepts the batch
Scenario: import_blocked
  Given missing values, unknown states, future times or conflicting duplicates
  When the mapper runs
  Then the checklist is BLOCKED with row-level reasons
  And no batch is emitted
Scenario: import_columns
  Given extra source columns
  When the checklist is prepared
  Then unmapped columns are listed
  And missing columns block the import
```
