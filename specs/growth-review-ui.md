# Spec: growth-review-ui
Status: draft

## MUST - Functional core
### Description
Make the existing growth-review backend usable from Results. Preserve all requested product functionality; this packet does not waive customer-workflow authoring, typed subscription experiment authoring, agent operation, CLI/MCP or provider acceptance.

### Requirements (EARS)
- The system shall return the app-owned unified subscription growth review in Results with missing-input guidance, separate evidence states, journey and experiment readouts and retained history bounded to 1000 rows through `review_controls`.
- The system shall save localized listing fields, supported platform and test surface through a labeled form bound to the selected app version while preserving the original text through `listing_form`.
- The system shall save a sourced benchmark with explicit metric, denominator, currency, segment, period, provenance, coverage and expiry through a labeled form through `reference_form`.
- The system shall store a comparison using only exact saved reference and current app-owned report selectors plus explicit operator classification, never caller-supplied account totals through `comparison_form`.
- The system shall append KEEP, REVISE or DEFER notes against an exact retained source hash without granting approval through `editorial_form`.
- The system shall preserve form inputs on error, suppress duplicate pending submissions and reject a changed app or version before saving through `safe_recovery`.
- The system shall show guide and source-specific analytics and export sanitized overview and exact-item reports through the existing printable PDF preview, preserving Unicode and excluding private form inputs through `scoped_reports`.
- The system shall retain existing Results controls, serve the new module through the static allowlist and verify actual desktop and mobile forms, durable readback, keyboard use, failures and PDF content through `ui_integration`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: review_controls
  Given the selected app workspace and app-owned evidence
  When `review_controls` is exercised
  Then its valid result is retained and invalid or changed scope cannot gain authority
Scenario: listing_form
  Given the selected app workspace and app-owned evidence
  When `listing_form` is exercised
  Then its valid result is retained and invalid or changed scope cannot gain authority
Scenario: reference_form
  Given the selected app workspace and app-owned evidence
  When `reference_form` is exercised
  Then its valid result is retained and invalid or changed scope cannot gain authority
Scenario: comparison_form
  Given the selected app workspace and app-owned evidence
  When `comparison_form` is exercised
  Then its valid result is retained and invalid or changed scope cannot gain authority
Scenario: editorial_form
  Given the selected app workspace and app-owned evidence
  When `editorial_form` is exercised
  Then its valid result is retained and invalid or changed scope cannot gain authority
Scenario: safe_recovery
  Given the selected app workspace and app-owned evidence
  When `safe_recovery` is exercised
  Then its valid result is retained and invalid or changed scope cannot gain authority
Scenario: scoped_reports
  Given the selected app workspace and app-owned evidence
  When `scoped_reports` is exercised
  Then its valid result is retained and invalid or changed scope cannot gain authority
Scenario: ui_integration
  Given the selected app workspace and app-owned evidence
  When `ui_integration` is exercised
  Then its valid result is retained and invalid or changed scope cannot gain authority
```

## SHOULD - Technical
- Reuse current typography, panels, modal, HTTP/CSRF and report infrastructure. Keep pure projections separate from event orchestration.
- Escape supplied text. Never export arbitrary DOM, credential controls or raw workspace objects.
- Native Print / Save as PDF remains user-controlled. Demonstrate actual PDF text and pagination with the isolated software QA browser.
- Existing history is immutable; correction uses a new identity and review notes grant no execution authority.
- Provider verification and measured outcomes remain separate from local source assertions.

## Authorized parameters
MAX_ROWS = 1000
RULE_VERSION = 2026
