# Spec: founder-source-recovery
Status: draft

## MUST - Functional core
### Description
Expose current customer and saved-account source problems in the unified founder
review. Existing detailed records remain immutable; no effect authority changes.

### Requirements (EARS)
- The system shall return recovery issues for saved customer workflows with expired, unavailable or stale-app evidence within the existing 1000 row history bound through `customer_recovery`.
- The system shall include each saved ads source whose current validation fails in the unified recovery list through `account_recovery`.
- The system shall return exact affected workflow or job identity, fixed repair guidance and source status without copying research excerpts or provider payloads through `scoped_recovery`.
- The system shall return NEEDS_INPUT while a current customer or account recovery issue exists and preserve LOCAL_REVIEW_AVAILABLE when all required sources are current through `review_state`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: customer_recovery
  Given a saved customer workflow whose source has expired or app scope changed
  When `customer_recovery` joins the founder review
  Then the exact workflow has a recovery issue and original research is retained
Scenario: account_recovery
  Given an app-owned saved ads report with invalidated connection binding
  When `account_recovery` joins the founder review
  Then the exact job has a recovery issue without exposing provider rows
Scenario: scoped_recovery
  Given research excerpts and source failure diagnostics
  When `scoped_recovery` constructs summary issues
  Then only fixed repair text, local identities and source states are included
Scenario: review_state
  Given all required review inputs and a recoverable source problem
  When `review_state` is calculated
  Then it requires input until current valid source evidence is supplied
```

## SHOULD - Integration
Reuse existing Results and report issue rendering. No new interface, credential,
provider action, publication or measured-outcome assertion is introduced.
