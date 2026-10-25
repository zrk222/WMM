# Spec: agent-usage-kpi
Status: draft

## MUST - Functional core
### Description
Correct lost provider token usage in successful app-owned agent jobs as part of UPG-08. Normalize bounded reported fields before durable storage, preserve unavailable telemetry and exclude raw payloads. Use the existing adapter and worker completion path. This packet does not complete the KPI catalog or Hypit workflow.

### Requirements (EARS)
- The system shall store provider-reported input, output and total token counts from canonical fields and compatible prompt/completion aliases through `usage_mapping`.
- The system shall reject conflicting aliases, booleans, negative counts, non-integer values and counts above 10000000 tokens from the stored usage observation through `usage_validation`.
- The system shall store exactly the explicitly reported cache-read, cache-write and reasoning token counts as distinct observations without adding nested subsets to total usage through `usage_details`.
- The system shall return reported, partial, unavailable or invalid telemetry states while preserving an observed zero and omitting unreported totals without computing a replacement through `usage_uncertainty`.
- The system shall persist normalized observations in successful selected-connection job results and preserve exact saved observations across restart and idempotent replay without another inference through `usage_persistence`.
- The system shall redact arbitrary usage fields and raw provider strings from saved usage diagnostics while retaining cost and quota as unknown through `usage_privacy`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: usage_mapping
  Given a successful provider response
  When `usage_mapping` is applied
  Then canonical input and output fields retain the reported prompt and completion counts
Scenario: usage_validation
  Given invalid values and conflicting field aliases
  When `usage_validation` is applied
  Then affected counts are omitted and diagnostics identify the closed field name
Scenario: usage_details
  Given reported cached input and reasoning output subsets
  When `usage_details` is applied
  Then subset observations remain distinct from the original total
Scenario: usage_uncertainty
  Given missing usage and an explicitly reported zero
  When `usage_uncertainty` is applied
  Then missing values remain absent and zero remains observed
Scenario: usage_persistence
  Given an approved isolated job and completed inference
  When `usage_persistence` is exercised across restart and replay
  Then the saved observation is unchanged and no repeated inference occurs
Scenario: usage_privacy
  Given arbitrary strings in provider usage
  When `usage_privacy` is applied
  Then no arbitrary string is stored and cost and quota remain unknown
```

## SHOULD - Technical
- Apply ECC API Connector Builder to shared public/local/native result mapping; do not introduce a new connector, authentication stack or automatic retry.
- Apply ECC AI Regression Testing to the exact lost-token bug and native/local path parity. Prove meaningful source mutants fail.
- Apply ECC cost guidance: no fabricated model prices, billed cost or quota; preserve observed subsets without double counting. This per-job contract is not an import of cumulative ECC session snapshots.
- No provider calls, credentials, operational data or paid generation are needed for isolated tests. Full authorized provider acceptance remains separate.

## Authorized parameters
MAX_TOKENS = 10000000
