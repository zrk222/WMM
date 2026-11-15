# Spec: campaign-owner-report-ui
Status: draft

## MUST - Functional core
### Description
Private report controls join exact saved campaign and monitor receipts with source measurement windows, without claiming attribution.

### Requirements (EARS)
- The system shall return a form for owner selection of an exact saved monitor and linked campaign, optional existing experiment and requested review window through `report_selection`.
- The system shall return a saved private report or a reviewed finite report schedule using current protected owner endpoints through `report_capture`.
- If owner, app, manifest or dialog changes, the system shall reject stale asynchronous actions and duplicate submissions through `report_context`.
- The system shall display source-window alignment, KPI unknowns, exact receipts, held commitments, descriptive comparison and next action through `report_evidence`.
- The system shall return a printable private report projection without raw creative, credential or provider payloads through `report_pdf`.

- Without a selected study, the private screen and printable report shall explain how to measure the campaign even when a saved authority or recovery reminder takes priority.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: report_selection
 Given saved owner monitor resources
 When `report_selection` selects a report source
 Then only linked campaign and exact selected IDs are submitted
Scenario: report_capture
 Given one exact review window and finite report schedule
 When `report_capture` confirms the returned plan hash
 Then the existing worker may save reports within the declared limits
Scenario: report_context
 Given a closed dialog or changed owner app or version
 When `report_context` returns a delayed response
 Then no stale view or request is applied
Scenario: report_evidence
 Given incomplete or unaligned source measurements
 When `report_evidence` displays a saved report
 Then source windows and unknown data remain explicit
Scenario: report_pdf
 Given a saved private report
 When `report_pdf` prints the projection
 Then no raw provider or secret fields are included
```
