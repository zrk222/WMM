# Spec: discovery-ui
Status: implementation
Parent: all discovery P1/P2 requirements and original/additive goal remain active.

## MUST
### Requirements (EARS)
- The system shall render an owner research workspace through `research_forms`, with separate industry narrative treatment and source labels, app outcome audience filters, observed hook beats transcript provenance baseline evidence rights and authentic proof inputs, rejecting unknown fields before saving at most 1000 items in baseline observations.
- The system shall store exact current source-bound reviews and collection requests through `research_writes`, preserving entered drafts after failure and retaining uncertain request identity until explicit read reconciliation or identical user-requested retry with at most 1 request per submission.
- The system shall return saved immutable collection details and at most 100 items in history pages through `research_results`, showing reasons observed qualified baseline-missing rights-missing counts, source currentness, distinct attention denominators and observation dates without inferring app sales.
- The system shall emit displayed research as PDF JSON and formula-safe CSV through `research_exports`, with no credentials or form inputs included and at most 1000 items in source decisions per saved collection.
- The system shall reject stale app identity late responses duplicate pending writes and unauthorized owners through `research_scope`, retaining 100000 views AND10times documented creator baseline and independent UGC intake eligibility.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: research_forms
  Given an authorized app owner and saved permitted sources
  When `research_forms` edits research inputs
  Then independent observations and interpretations remain explicit
Scenario: research_writes
  Given current source and app hashes
  When `research_writes` receives an uncertain response
  Then the exact request remains available for reconciliation without automatic resubmission
Scenario: research_results
  Given immutable saved collections
  When `research_results` reads a selected snapshot
  Then source qualification and evidence gaps have distinct observed values
Scenario: research_exports
  Given a displayed saved collection
  When `research_exports` creates downloadable reports
  Then the values match saved decisions and private inputs are excluded
Scenario: research_scope
  Given a changed app or owner identity
  When `research_scope` receives an old response
  Then no private response is shown in the new context
```

## Required follow-up
This packet implements source review and collection browsing/export, not provider collection or scheduled watch execution. Watch/attempt UI, existing brief/editor/Hypit packet consumption and real cross-platform/client/device acceptance remain required. Research status grants no reuse execution publication or measured sales. Existing downstream exact human/standing authority remains unchanged.
