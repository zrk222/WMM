# Spec: subscription-authoring-ui
Status: draft

## MUST - Functional core
### Description
Finish founder authoring for typed paywall/offer experiments and their explicit billing source records. Use structured labeled forms and the existing validated service. No live paywall change or purchase is performed.

### Requirements (EARS)
- The system shall store an explicit tested subscription configuration with product, offer, price, renewal terms, placement, access method and dated billing/restore/eligibility observations through `billing_authoring`.
- The system shall store a paywall or offer experiment using two selected app-owned cohorts and exact saved billing configurations, preserving existing preregistration, comparability and maturity validation through `typed_registration`.
- The system shall reject changed app/version and source hashes, suppress duplicate pending submits and retain form inputs after errors through `safe_drafts`.
- The system shall return saved configuration details and sanitized printable reports with source scope, dates and observed terms without promoting supplied eligibility to provider verification through `review_reports`.
- The system shall retain all existing Results flows and verify authoring at desktop width 1440 px and mobile width 390 px with actual API readback and negative/recovery behavior through `browser_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: billing_authoring
  Given current selected app evidence
  When `billing_authoring` is exercised
  Then valid data is retained and invalid source or app scope is rejected
Scenario: typed_registration
  Given current selected app evidence
  When `typed_registration` is exercised
  Then valid data is retained and invalid source or app scope is rejected
Scenario: safe_drafts
  Given current selected app evidence
  When `safe_drafts` is exercised
  Then valid data is retained and invalid source or app scope is rejected
Scenario: review_reports
  Given current selected app evidence
  When `review_reports` is exercised
  Then valid data is retained and invalid source or app scope is rejected
Scenario: browser_proof
  Given current selected app evidence
  When `browser_proof` is exercised
  Then valid data is retained and invalid source or app scope is rejected
```

## SHOULD - Technical
- Select actual billing records and freeze their configuration. Never invent a default SKU, price, eligibility or tested result. Whole-day durations match the existing contract.
- Reuse existing report and field helpers. No arbitrary DOM/state export or credential capture. Existing experiment lifecycle controls remain in use.
- Explicit checkboxes record operator-reported observations and do not authenticate purchase or provider acceptance.

## Authorized parameters
Synthetic browser fixture guardrails only; these values are never form defaults or production policy.
min_retention_rate = 0.2
max_refund_fraction = 0.1
min_contribution_minor = 0
max_acquisition_minor = 5000
