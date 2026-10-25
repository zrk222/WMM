# Spec: cohort-refund-semantics
Status: implementation

## MUST - Functional core

### Description
This bounded correction aligns derived manual-cohort contribution with the event-ledger refund treatment.

### Requirements (EARS)
- The system shall return `contribution_minor` as `net_proceeds_minor` minus `delivery_cost_minor`, and `contribution_after_acquisition_minor` as `net_proceeds_minor` minus `delivery_cost_minor` minus `acquisition_cost_minor`, where supplied `net_proceeds_minor` already equals gross proceeds minus `refunds_minor` and the `refunds_minor` field remains unchanged in counts; with 0 installs or 0 paid customers the corresponding `activation_rate`, `paid_conversion`, and `paid_cac_minor` fields are null; when `mature` is false, the system shall return `INCONCLUSIVE` without contribution fields.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: No refund
  Given `net_proceeds_minor` is 2000 and `refunds_minor` is 0
  When both manual and event-ledger reports are calculated
  Then `contribution_minor` is 1900
  And `contribution_after_acquisition_minor` is 1600

Scenario: One partial refund
  Given gross proceeds are 2000, `refunds_minor` is 500, and `net_proceeds_minor` is 1500
  When both reports are calculated
  Then `refunds_minor` remains 500 in manual counts and the ledger report
  And `contribution_minor` is 1400
  And `contribution_after_acquisition_minor` is 1100

Scenario: Full refund
  Given gross proceeds are 2000, `refunds_minor` is 2000, and `net_proceeds_minor` is 0
  When both reports are calculated
  Then `contribution_minor` is -100
  And `contribution_after_acquisition_minor` is -400

Scenario: Zero denominators
  Given there are 0 installs and 0 paid customers
  When the mature report is calculated
  Then `activation_rate`, `paid_conversion`, and `paid_cac_minor` are null

Scenario: Immature follow-up
  Given `mature` is false
  When the report is calculated
  Then `INCONCLUSIVE` is returned and contribution fields are unavailable
```

## SHOULD - Technical and structural
- Keep refund amount separately visible and never mutate input records.
- Use only synthetic in-memory fixtures; do not access operational databases or provider APIs.
- The arithmetic correction adds no I/O, storage, UI, or network calls and uses a fixed sequence of subtraction operations.

## WON'T - Out of scope
- No change to ledger ingestion, immutable event history, attribution, currencies, or maturity policy.
- No reinterpretation, migration, or re-keying of saved financial records.
- No UI, export, provider, or release change.
