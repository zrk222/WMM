# Spec: progressive-workflow
Status: draft

## MUST - Functional core
### Description
Apply report FR-2.1 and the workflow portion of FR-2.3/8.3. Focus the existing
guided journey on the next unresolved step; retain all stages, critical blockers,
input counts, worker health and original approval boundaries.

### Requirements (EARS)
- The system shall render the recommended unresolved stage expanded and place other stages inside an accessible full-workflow disclosure through `progressive_focus`.
- The system shall return a visible summary of critical findings across all stages even when other stages are collapsed through `progressive_blockers`.
- The system shall render explicit saved-input approved-execution and observed-outcome explanations without treating input readiness as completed execution through `progressive_states`.
- The system shall render all stages when no next stage exists and preserve every stage action and verification detail through `progressive_complete`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: progressive_focus
  Given an unresolved recommended stage
  When `progressive_focus` renders the journey
  Then that stage is expanded and every other stage remains accessible
Scenario: progressive_blockers
  Given a critical finding in a later stage
  When `progressive_blockers` renders collapsed stages
  Then the finding remains visible in the top summary
Scenario: progressive_states
  Given saved inputs but no measured result
  When `progressive_states` explains progress
  Then readiness never implies execution or measured outcome
Scenario: progressive_complete
  Given all local stage inputs ready
  When `progressive_complete` renders
  Then every stage and verification action remains available
```
