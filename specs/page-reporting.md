# Spec: page-reporting
Status: draft

## MUST - Functional core
### Description
All ten top-level pages receive a brief explainer, relevant analytics and a PDF-report flow. Secondary dialogs and tool panels remain a separately tracked coverage packet. Counts describe loaded local data, never measured growth or provider permission.

### Requirements (EARS)
- The system shall return a brief purpose and next step for all ten top-level views through `page_explainers`.
- The system shall return relevant app-scoped operational metrics and explicit unknown states without inventing growth through `page_analytics`.
- The system shall store exact page, app, filters, loaded time and evidence caveats in a sanitized report projection through `report_scope`.
- The system shall return a Unicode printable report with an explicit Save as PDF interaction on every top-level view through `pdf_export`.
- The system shall reject unknown views and changed app scope and exclude credentials and arbitrary raw workspace data through `report_privacy`.
- The system shall return actionable feedback when a report window is blocked or selected data is unavailable through `report_recovery`.
- The system shall return `overview_story` in plain user language explaining the user's mission, how WMM helps, expected artifacts and human control without promising business results.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: page_explainers
  Given a selected app and supported page
  When `page_explainers` is exercised
  Then its source-bound behavior is observed and invalid scope is rejected
Scenario: page_analytics
  Given a selected app and supported page
  When `page_analytics` is exercised
  Then its source-bound behavior is observed and invalid scope is rejected
Scenario: report_scope
  Given a selected app and supported page
  When `report_scope` is exercised
  Then its source-bound behavior is observed and invalid scope is rejected
Scenario: pdf_export
  Given a selected app and supported page
  When `pdf_export` is exercised
  Then its source-bound behavior is observed and invalid scope is rejected
Scenario: report_privacy
  Given a selected app and supported page
  When `report_privacy` is exercised
  Then its source-bound behavior is observed and invalid scope is rejected
Scenario: report_recovery
  Given a selected app and supported page
  When `report_recovery` is exercised
  Then its source-bound behavior is observed and invalid scope is rejected
Scenario: Main page story
  Given a person opening WMM for their app
  When `overview_story` is read
  Then the person sees what to bring, how work progresses, what they receive and which outcomes remain uncertain
```

## SHOULD - Technical
- Typed projection; no DOM capture, external transmission or arbitrary raw JSON export.
- Weekly review is a separately labeled portfolio page and must respect the displayed page coverage and failures.
- Zero counts require a loaded array; a missing source is unavailable. Dates distinguish browser loading from underlying source freshness.
- Results retain per-cohort denominators, horizons and currencies; never sum incompatible monetary amounts.
- Printing uses a dedicated same-origin report with escaping, Unicode and print pagination; opening a print dialog alone is not proof of a PDF.
- Client interaction is keyboard accessible and usable at desktop and mobile sizes.
- No publication, spend, provider mutation, production activation or credentials are authorized.
- Every existing and requested feature remains in scope for full product completion. Staged packets cannot hide or remove unfinished features to manufacture acceptance.

## Authorized parameters
The report text bound prevents unbounded headings; report rows are capped with explicit truncation.
MAX_TEXT = 1000
MAX_ROWS = 100
