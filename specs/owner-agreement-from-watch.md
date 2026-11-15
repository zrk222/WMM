# Spec: owner-agreement-from-watch
Status: approved

## MUST - Functional core

### Requirements (EARS)

- When the owner opens Watch the work, the system shall display `watch_agreement_entry` next to saved campaign controls and retain existing setup and readiness routes.
- When the current session lacks app owner access, the system shall return `agreement_signin_repair` without reading private scope histories. The system shall show the existing sign-in or first-owner action when applicable.
- When the app, owner or modal changes before a read completes, the system shall reject the old response through `agreement_scope_guard` without issuing an approval or dispatching work.

### Acceptance criteria (Gherkin)

```gherkin
Scenario: watch_agreement_entry
  Given an owner viewing Watch the work at narrow or wide width
  When the `watch_agreement_entry` path runs
  Then the existing unified agreement opens without navigating to advanced controls

Scenario: agreement_signin_repair
  Given a guest or a signed-in account without the owner role
  When the `agreement_signin_repair` path runs from any entry
  Then the UI explains the next step and sends no scope-history requests

Scenario: agreement_scope_guard
  Given a pending agreement read
  When the `agreement_scope_guard` path runs after switching the selected app, signing out, or closing the modal
  Then the stale response does not replace the current screen or start an effect
```

## Bounds

Reuse the existing redacted agreement and explicit identity actions. Server owner checks remain authoritative. No activation, scope change, provider call, app creation or external account sign-in starts on opening the agreement.
