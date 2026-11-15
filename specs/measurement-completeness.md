# Spec: measurement-completeness
Status: approved

## MUST - Functional core
### Description
Make missing measurement evidence actionable, calculate explicitly scoped economics and show unsuccessful experiment history.
### Requirements (EARS)
- The system shall return CAC and D7/D30 ROAS with explicit numerator basis, denominator, currency and attribution scope under `economics`.
- The system shall return null metrics with concrete repair actions for absent, partial, immature or mismatched evidence under `unavailable_data`.
- The system shall store install-relative observation cutoffs and deduplicate acquired payers and financial events under `cohort_windows`.
- The system shall emit every retained assessment including negative, blocked and inconclusive results without replacing prior history under `experiment_history`.
- The system shall emit matching economics and experiment-history details in owner UI and exportable reports under `reporting`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: economics
 Given app-scoped supplied measurement evidence
 When `economics` executes
 Then its source-bound result and missing-input actions remain explicit
Scenario: unavailable_data
 Given app-scoped supplied measurement evidence
 When `unavailable_data` executes
 Then its source-bound result and missing-input actions remain explicit
Scenario: cohort_windows
 Given app-scoped supplied measurement evidence
 When `cohort_windows` executes
 Then its source-bound result and missing-input actions remain explicit
Scenario: experiment_history
 Given app-scoped supplied measurement evidence
 When `experiment_history` executes
 Then its source-bound result and missing-input actions remain explicit
Scenario: reporting
 Given app-scoped supplied measurement evidence
 When `reporting` executes
 Then its source-bound result and missing-input actions remain explicit
```

## SHOULD - Technical
Reuse the existing immutable cohort/event and experiment assessment ledgers. No parallel failure ledger. Never infer missing spend, zero acquisitions, gross revenue or causal lift. Old inputs remain accepted but insufficient scoped economics remain unavailable. User-supplied matching is labeled supplied, not provider-verified. Signing and outcomes remain separate mechanics.
