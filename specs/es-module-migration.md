# Spec: es-module-migration
Status: approved

## MUST - Functional core
### Description
Replace the shared classic-script scope of the dashboard with a native browser module
entry and explicit controller imports. Preserve owner consent, private state,
rendering, agent setup and campaign authority behavior. Audit the preceding
maintainability commits separately from proving production provider outcomes.

### Requirements (EARS)
- The system shall load the dashboard through one module entry under `module_entry` and shall resolve controller dependencies using explicit relative imports.
- The system shall store one live workspace state object under `shared_state` and shall start the dashboard only after its dependency graph is initialized.
- The system shall serve every local transitive module with JavaScript MIME under `module_routes` and shall reject undeclared static paths.
- The system shall reject unapproved and not-yet-due external actions under `authority_preserved` and shall store the OFF state across reload.
- The system shall return the existing CommonJS-compatible feature API under `library_compatibility` through an explicit compatibility boundary.
- The system shall reject unresolved imports, missing exports and module syntax failures under `module_validation`.
- The system shall record inspected commits, actual test results and unresolved findings under `audit_evidence` without claiming live effects from fixture tests.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: module_entry
 Given a dashboard page
 When `module_entry` starts
 Then one native module entry loads and classic controller script tags are absent
Scenario: shared_state
 Given two screen controllers
 When `shared_state` selects a workspace
 Then both use the same live state and startup executes once
Scenario: module_routes
 Given the module graph
 When `module_routes` serves its files
 Then declared modules return script content and unknown files remain unavailable
Scenario: authority_preserved
 Given synthetic owner automation
 When `authority_preserved` reviews and schedules work
 Then no effect occurs before approval or due time and cancellation survives reload
Scenario: library_compatibility
 Given a pure feature library
 When `library_compatibility` loads in its supported host
 Then existing feature behavior is preserved without exposing app state globally
Scenario: module_validation
 Given an invalid module dependency
 When `module_validation` checks the graph
 Then a missing module or export fails validation
Scenario: audit_evidence
 Given the reviewed source candidate
 When `audit_evidence` records observations
 Then tested source hashes and remaining limits are explicit
```

## SHOULD - Technical
- Native browser ESM; no bundler, framework or runtime dependency installation.
- Compatibility libraries remain separately testable as CommonJS; their globals
  are adapted at one named boundary. Application controllers use imports.
- Keep existing callback pages independent; migration covers the dashboard.
- Do not export credentials, owner state or generic mutation helpers to window.
- Prove the real module graph in Chromium; legacy isolated-function VM tests
  cannot substitute for browser module linking.
