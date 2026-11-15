# Spec: feature-library-modules
Status: approved

## MUST - Functional core
### Description
Retire three compatibility globals without changing analytics, campaign planning or MMP import behavior.
### Requirements (EARS)
- The system shall return three pure library exports through explicit native imports under `module_linking`.
- The system shall return existing library outputs and reject invalid inputs with existing errors under `behavior_parity`.
- The system shall reject missing exports or compatibility-library count growth under `module_ratchet`.
- The system shall reject JSDoc type violations in analytics-inventory, campaign-plan and mmp-import-model under `library_types`.
### Acceptance criteria (Gherkin)
```gherkin
Scenario: module_linking
 Given three migrated pure libraries
 When `module_linking` executes
 Then explicit imports resolve without global side effects
Scenario: behavior_parity
 Given current library fixtures
 When `behavior_parity` executes
 Then all prior expected outputs remain unchanged
Scenario: module_ratchet
 Given the approved compatibility budget
 When `module_ratchet` executes
 Then compatibility library growth fails
Scenario: library_types
 Given incorrect input types in a negative fixture
 When `library_types` executes
 Then the checker rejects the fixture
```

## SHOULD - Technical
Convert analytics-inventory, campaign-plan and mmp-import-model only. Preserve local authority, provider boundaries and receipt meaning. No new product operations, no framework migration and no runtime dependency.
