# Spec: campaign-owner-reports
Status: draft

## MUST - Functional core
### Description
Save private source-bound owner reports from existing campaign receipts, optional monitor observations, app KPI projection and optional existing experiment assessment. Owner capture and finite report plans authorize local report storage only.

### Requirements (EARS)
- The system shall reject foreign app, owner, monitor, scope, experiment and changed approval hashes through `source_boundary`.
- With an owned campaign scope and no monitor selected, the system shall save the existing campaign receipts and identify monitoring as unavailable without creating a monitor or reading a provider.
- The system shall store an immutable current report with source hashes, observation dates, retained commitments, missing KPI states, experiment maturity and one next action through `private_report`.
- The next action may use an experiment recommendation only when both arms match the report acquisition window and a saved assessment matches the definition and was created between the declared analysis date and report capture. App-wide metrics remain descriptive and cannot substitute for that assessment. An unselected monitor does not block the evidence recommendation; a selected monitor with missing or blocked observations retains recovery priority.
- The system shall return a previous snapshot comparison only for the same app, scope approval, metric definitions and declared measurement window through `comparison_boundary`.
- The system shall require explicit owner capture or exact hash activation of a plan with cadence from 30 to 86400 seconds, one through 100 reports and expiry within 7 days through `finite_authority`.
- The system shall enqueue at most 20 due local report jobs per tick and reject changed host, app, owner or job lease inputs through `durable_execution`.
- The system shall store no report from an unapproved request and make no provider read, external message, publishing or campaign mutation through `no_effect`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: source_boundary
  Given exact current owned resources and foreign or changed resource variants
  When `source_boundary` captures a report
  Then only matching current owner and app source bindings are accepted
Scenario: private_report
  Given unknown and pending campaign results and missing KPI observations
  When `private_report` saves existing evidence
  Then hashes and dates are retained and missing values remain unknown without growth claims
Scenario: comparison_boundary
  Given previous matching and incompatible report definitions
  When `comparison_boundary` reads the next report
  Then only compatible snapshots are compared and no causal lift is inferred
Scenario: finite_authority
  Given explicit owner choices and an unapproved plan
  When `finite_authority` activates report capture
  Then an exact current summary hash and finite bounds are required
Scenario: durable_execution
  Given a due approved plan and changed lease or revoked role
  When `durable_execution` ticks and executes after restart
  Then work is idempotent and changed authority is rejected
Scenario: no_effect
  Given saved local evidence and forbidden provider or messaging adapters
  When `no_effect` generates a private report
  Then local snapshot storage succeeds without provider or outbound effects
```

## SHOULD - Technical
- Existing ios_reports.snapshot supplies metric rows with source windows retained. A selected review window is not proof that every source aligns; report this boundary explicitly.
- Reuse saved experiment analysis; do not invoke effectful assessment or fabricate attribution.
- Read-only report generation can continue after a campaign or monitor is OFF, but current app/owner and exact resource summary hashes remain mandatory.
- Select an existing scope and optionally its existing monitor; report storage never grants provider authority.
