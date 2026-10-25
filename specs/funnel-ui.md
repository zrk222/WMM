# Spec: funnel-ui
Status: implementation

## MUST - Functional core
### Requirements (EARS)
- The system shall return the app-sales workspace in Results through `funnel_entry`, explaining the purpose, required inputs, saved actions, delivered stage results and concrete next steps without webinar or coaching defaults.
- The system shall create immutable app-sales plans through `funnel_authoring`, selecting current creative and optional customer sources, an existing matching cohort, outcome, hook, CTA, app destination, actual free and paid capabilities and an editable graph of at most32 stages with declared units and populations.
- The system shall import one observation or at most500 JSON observations through `funnel_observations`, preserving declared stage, source hash, identity scope, acquisition window, observed time, coverage and count, with unknown count represented as null and observed zero retained.
- The system shall show bounded saved-plan and observation pages and complete stage reports through `funnel_results`, distinguishing observed, partial, missing, conflicting and stale states, eligible denominators and withheld ratios while reading payment and refund values only from the existing ledger.
- The system shall emit the displayed source-bound report through `funnel_exports` as printable PDF, JSON and formula-safe CSV with app, cohort, currency, timestamps, definitions and uncertainty scope.
- The system shall preserve drafts and reject stale app or identity context through `funnel_recovery`, deduplicate pending submissions with a request deadline of 30 seconds, retain at most1 in-flight request body per dialog and uncertain request bodies for explicit reconciliation or exact idempotent retry, and never automatically replay a write or approve provider actions.
- The system shall return labelled keyboard workflows at1440 and390 pixels through `funnel_accessibility`, with labelled controls, focus on dialog entry, announced progress and errors, no page overflow and escaped saved text in pages and reports.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: funnel_entry
  Given the selected app Results page
  When `funnel_entry` opens app-sales funnels
  Then its purpose inputs actions outputs and prerequisites are visible
Scenario: funnel_authoring
  Given current app creative sources and a matching saved cohort
  When `funnel_authoring` saves a customized stage graph
  Then the same source hashes and declared app-sales outcome persist after reload
Scenario: funnel_observations
  Given an exact current saved funnel
  When `funnel_observations` imports single or bounded batch evidence
  Then zero partial and unknown values remain distinct and invalid input preserves the draft
Scenario: funnel_results
  Given saved definitions and more than100 observations
  When `funnel_results` pages evidence and reads the report
  Then every saved observation is reachable and complete report values include later pages
Scenario: funnel_exports
  Given the displayed stage report
  When `funnel_exports` creates PDF JSON or CSV
  Then exported values agree with the exact displayed source-bound report
Scenario: funnel_recovery
  Given a rejected or uncertain write
  When `funnel_recovery` inspects saved state or explicitly retries identical input
  Then there is no automatic replay cross-app draft leak or changed request body
Scenario: funnel_accessibility
  Given desktop and narrow mobile viewports
  When `funnel_accessibility` navigates forms results and exports by keyboard
  Then focus labels progress errors and saved text remain readable without page overflow
```

## WON'T - Out of scope
No provider dispatch, literal webinar workflow, coaching price ladder, spending, publication, automatic live paywall configuration or inferred person-level transition. Real provider acceptance and all remaining parent scope remain required. The same immutable HTTP domain services and agent operations stay authoritative.
