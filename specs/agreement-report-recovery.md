# Spec: agreement-report-recovery
Status: draft

## MUST - Functional core
### Requirements (EARS)
- When a private agreement report is opened, the system shall display the saved stop rules, `OFF` guidance and current recovery action through `report_recovery`.
- When a batch is selected, the system shall display its saved approval deadline, batch fingerprint and each item fingerprint, local job and provider intent state through `schedule_evidence`.
- The system shall return a report without private campaign copy, links, credentials or job payloads through `private_export`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: report_recovery
  Given a combined agreement with an uncertain dispatch
  When the owner opens the private report
  Then it displays the stop rules, OFF guidance and the instruction to reconcile before retrying

Scenario: schedule_evidence
  Given a saved batch with a succeeded local job and a pending provider intent
  When the owner opens the private report
  Then the report identifies both states separately and includes the saved deadline and fingerprints

Scenario: private_export
  Given a selected campaign containing private copy or credentials
  When the owner opens the private report
  Then there is no copy or link or credential or job payload in the report
```
