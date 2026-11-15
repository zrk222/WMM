# Spec: packaged-first-value-current-form
Status: draft

## MUST - Functional core
### Requirements (EARS)
- When the package browser submits its exact synthetic app fixture, the system shall accept an empty optional discovery link through `current_form`.
- If the synthetic form includes a nonempty discovery link, the system shall reject it through `fixture_boundary`.
- If a setup request does not match the exact synthetic fixture, the system shall return a synthetic 422 response without sending the request to the runtime through `fixture_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: current_form
  Given the current manual app form in an isolated workspace
  When the browser saves the six required fields without optional discovery
  Then the synthetic app is created and its four goal packets can be downloaded
  And restart preserves the app and selected goal

Scenario: fixture_boundary
  Given a package browser request outside the exact setup fixture
  When the browser submits the request
  Then it receives a fixture failure and creates no app
```
