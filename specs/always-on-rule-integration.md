# Spec: always-on-rule-integration
Status: approved

## MUST - Functional core

### Requirements (EARS)

- When an owner enables the `private_report_consent` integration, the system shall store the selected report, its fingerprint, its current sources and a saved rule version in the finite schedule.
- When a new qualifying result review matches, the system shall use `private_report_effect` to save one private campaign report and bind its identifier and fingerprint to the same committed evaluation receipt.
- When current authority lapses, or the same approval already produced a report, was dismissed, is incompatible or is in cooldown, the system shall return no new report through `private_report_boundary`. The system shall never execute external effects from a rule.
- Where the owner starts scheduled reviews in Results, the system shall display `private_report_controls` to choose a private report, inspect the saved result and turn off scheduled work.

### Acceptance criteria (Gherkin)

```gherkin
Scenario: private_report_consent
  Given an owner and a saved rule set that supports private Results reports
  When the `private_report_consent` path runs with a foreign, stale, or valid template
  Then only the valid template and its current sources are pinned

Scenario: private_report_effect
  Given a due schedule and a matching open results review with no prior report under its approval
  When the `private_report_effect` path runs and the worker repeats the slot or restarts
  Then the original report and the evaluation share one verifiable committed receipt

Scenario: private_report_boundary
  Given missing evidence, an already handled or dismissed recommendation, revoked authority or an external action
  When the `private_report_boundary` path runs
  Then no extra report for that input or external provider action is dispatched

Scenario: private_report_controls
  Given a private report and saved rules
  When the `private_report_controls` path runs in Results
  Then the owner sees what will be saved, can choose a template and can stop future work
```

## Bounds

The owner opts in to repeat one existing report selection, including its fixed measurement dates. Only an enabled AUTO_WITHIN_GRANT rule proposing review_result through reports.read with OWNER_REVIEW qualifies. A manual run never acts. An existing open match can run after its cooldown expires. An approval saves at most one report, even if the wider app facts change. Dismissed exact recommendations cannot run. A MATCH with missing or incompatible branches cannot run. A deliberate missing predicate is an ordinary match when the evaluator reports no gaps. When a study is selected, the report window must match the study dates; report and study keep distinct source records and no attribution is inferred. An unmatched or suppressed recommendation keeps its ordinary inbox record. The integration adds no provider authority, network calls, spend or new agent operation. The owner still reviews the report and all proposed external changes.

## Authorized parameters

These are offline verification fixtures, not runtime defaults.
START = 2026
START = 11
START = 15
START = 7
max_workers = 2
limit = 3
