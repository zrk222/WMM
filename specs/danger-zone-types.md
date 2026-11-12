# Spec: danger-zone-types
Status: approved

## MUST - Functional core
### Description
Type five newly enrolled danger-zone modules without changing runtime validation or SQL semantics.
### Requirements (EARS)
- The system shall return validated request and normalized campaign shapes through explicit types under `typed_boundary`.
- The system shall return generated row mappings only after actual complete-row fetches and null checks under `row_contracts`.
- The system shall reject missing parameter or return annotations on named security-sensitive functions under `danger_annotations`.
- The system shall emit Pyright standard results over the maintained Python registry only under `standard_profile`.
- The system shall reject the same invalid inputs and retain existing authority checks without runtime casts changing values under `runtime_preserved`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: typed_boundary
 Given a typed security boundary
 When `typed_boundary` executes
 Then its declared contract and regression checks pass
Scenario: row_contracts
 Given a typed security boundary
 When `row_contracts` executes
 Then its declared contract and regression checks pass
Scenario: danger_annotations
 Given a typed security boundary
 When `danger_annotations` executes
 Then its declared contract and regression checks pass
Scenario: standard_profile
 Given a typed security boundary
 When `standard_profile` executes
 Then its declared contract and regression checks pass
Scenario: runtime_preserved
 Given a typed security boundary
 When `runtime_preserved` executes
 Then its declared contract and regression checks pass
```

## SHOULD - Technical
Use object for unvalidated input and narrowed shapes after existing validation. No blanket Any or ignore rules. Add five newly enrolled core files. Keep fetchone partial projections distinct from generated full-row mappings.
