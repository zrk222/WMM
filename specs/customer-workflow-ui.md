# Spec: customer-workflow-ui
Status: draft

## MUST - Functional core
### Description
Connect the existing customer-workflow store to founder authoring, immutable revisions, source-linked review and reporting. All requested product features remain mandatory; this packet does not close typed subscription authoring, agent autonomy, CLI/MCP or expanded provider access.

### Requirements (EARS)
- The system shall store a labeled customer workflow with buyer, narrow behavior, desired outcome, explicit release/locale/currency and prototype test through `customer_authoring`.
- The system shall store one through 100 public observations and one through 20 proposed features with exact source references and falsifiable validation, plus one through 20 excluded features with reasons through `source_linkage`.
- The system shall retain draft inputs and selected links when adding or removing rows and after rejected saves, suppress duplicate pending submits and reject changed app/version through `draft_recovery`.
- The system shall return app-owned saved history and exact-source details, and prepare a new immutable version while preserving the original record through `immutable_revision`.
- The system shall show current source freshness, unavailable source counts, imported provenance and stale app scope without inferring verified demand or paid behavior through `truthful_readout`.
- The system shall return sanitized selected-app and exact-item printable PDF reports bounded to 1000 rows with explainers, counts, dates, original source/feature/exclusion links and limitations while excluding raw state and unsaved forms through `customer_reports`.
- The system shall retain existing Results controls and verify authoring with history bounded to 1000 rows, desktop width 1440 px, mobile width 390 px, durable readback, row edits, negative/recovery/scope behavior, keyboard and generated PDF text through `customer_ui_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: customer_authoring
  Given the selected app and supplied public research
  When `customer_authoring` is exercised
  Then valid results remain source-linked and invalid or changed scope cannot gain authority
Scenario: source_linkage
  Given the selected app and supplied public research
  When `source_linkage` is exercised
  Then valid results remain source-linked and invalid or changed scope cannot gain authority
Scenario: draft_recovery
  Given the selected app and supplied public research
  When `draft_recovery` is exercised
  Then valid results remain source-linked and invalid or changed scope cannot gain authority
Scenario: immutable_revision
  Given the selected app and supplied public research
  When `immutable_revision` is exercised
  Then valid results remain source-linked and invalid or changed scope cannot gain authority
Scenario: truthful_readout
  Given the selected app and supplied public research
  When `truthful_readout` is exercised
  Then valid results remain source-linked and invalid or changed scope cannot gain authority
Scenario: customer_reports
  Given the selected app and supplied public research
  When `customer_reports` is exercised
  Then valid results remain source-linked and invalid or changed scope cannot gain authority
Scenario: customer_ui_proof
  Given the selected app and supplied public research
  When `customer_ui_proof` is exercised
  Then valid results remain source-linked and invalid or changed scope cannot gain authority
```

## SHOULD - Technical
- Use labeled repeatable rows and typed payloads, not raw JSON authoring. Keep source IDs stable when rows move. Removing a source removes its selection and visibly requires feature relinking before save.
- Reuse existing modal, app/version checks, HTTP/CSRF and sanitized report rendering. Never copy arbitrary DOM or raw workspace into reports.
- Corrections create new entry IDs and preserve original history. Imported or expired research remains visible and cannot become proof of demand.
- Prove field retention, scope, recovery and PDF pagination in isolated browsers with synthetic records; no actual customer contact, credential access, provider mutation or publication.

## Authorized parameters
MAX_HISTORY = 1000
MAX_SOURCES = 100
MAX_FEATURES = 20
MAX_EXCLUSIONS = 20
