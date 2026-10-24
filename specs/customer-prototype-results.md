# Spec: customer-prototype-results
Status: draft

## MUST - Functional core
### Description
Record a consented prototype task observation alongside one immutable customer
workflow version. Reuse current customer HTTP, CLI/MCP, export and report paths.
An operator-supplied observation does not establish demand or paid behavior.

### Requirements (EARS)
- The system shall store an optional prototype result containing task outcome, observed time, feedback up to 500 characters, evidence SHA256, consent, up to 20 tested feature identities and optional duration through `prototype_record`.
- The system shall reject future observations, unknown or repeated tested feature identities, missing consent, email contact details, unsupported outcomes and durations outside 0 through 86400 seconds through `prototype_validation`.
- The system shall retain existing workflow data and hashes when no prototype result was supplied and preserve old versions after a new result is saved through `prototype_history`.
- The system shall render optional add and remove result controls, labeled inputs and saved result details while preserving failed form inputs through `prototype_ui`.
- The system shall return prototype-result version counts and completed-task version counts with supplied-evidence labels and export saved outcome, feedback and evidence references in PDF reports through `prototype_reporting`.
- The system shall accept the same result through existing customer.save HTTP, CLI and MCP operations while enforcing current app scope and immutable replay through `prototype_agent`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: prototype_record
  Given a consented completed or incomplete prototype task observation
  When `prototype_record` is saved and the database reopens
  Then exact outcome, feedback and evidence references persist
Scenario: prototype_validation
  Given invalid consent dates duration identity or feedback
  When `prototype_validation` runs
  Then no result is stored and original workflow versions remain unchanged
Scenario: prototype_history
  Given existing legacy workflow data
  When `prototype_history` is read and a revised result version is saved
  Then original hashes and source data remain unchanged
Scenario: prototype_ui
  Given desktop1440 and mobile390 users
  When `prototype_ui` records and reviews a result using the keyboard
  Then labels, input recovery, app isolation and saved feedback remain usable
Scenario: prototype_reporting
  Given a saved supplied prototype observation
  When `prototype_reporting` exports the exact workflow
  Then outcome feedback evidence and provenance appear without private draft data
Scenario: prototype_agent
  Given an admitted caller using customer.save
  When `prototype_agent` submits the same typed result through the fixed operation
  Then it reaches the shared validator without new execution or approval authority
```

## Authorized parameters
MAX_DURATION_SECONDS = 86400
MAX_FEEDBACK_CHARACTERS = 500
MAX_TESTED_FEATURES = 20
