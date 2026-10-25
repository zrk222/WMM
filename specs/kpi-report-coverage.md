# Spec: kpi-report-coverage
Status: draft

## MUST - Functional core
### Description
Trace the user KPI report and all eight prior families to current code coverage,
canonical definitions, missing collectors and complete UI/agent/export acceptance.

### Requirements (EARS)
- The system shall record every reported KPI and prior family with explicit incomplete status and acceptance through `kpi_coverage`.
- The system shall record reviewed source hashes and verified provider permission requirements through `kpi_sources`.
- The system shall record autonomous media workflow analytics in the existing active goal through `kpi_goal`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: kpi_coverage
  Given the KPI report and prior eight families
  When `kpi_coverage` is checked
  Then every named KPI retains its definition and required acceptance
Scenario: kpi_sources
  Given existing metrics and source permissions
  When `kpi_sources` validates the review
  Then existing calculations and missing collection paths remain distinct
Scenario: kpi_goal
  Given user requested optional media intake and autonomy
  When `kpi_goal` appends scope
  Then import discovery edits execution and outcomes remain required
```
