# Spec: experiment-instrumentation
Status: draft

## MUST — Functional core
### Description
Produce an app/release/locale/experiment-bound browser integration bundle from
the saved tracking proposal. A reusable browser module wraps the existing app
PostHog client; it does not install a dependency or initialize a provider key.
The operator can review and download exact files and a source-hashed installation
contract. A downloaded package is not installed or live campaign evidence.

### Requirements (EARS)
- The system shall return a source-hashed `instrumentation_bundle` containing a fixed browser module, exact config, installation example and verification instructions without credentials.
- The system shall reject `SDK_PREREQUISITES_REQUIRED` before flag evaluation when the existing client lacks the documented remote evaluation, person-profile or identity prerequisites.
- When the app grants current consent and exposes a matching opaque identified user, the system shall return a fresh registered `control` or `treatment` variant within the acquisition window.
- The system shall store `sticky_assignment` atomically across same-origin browser tabs and reject variant changes instead of moving a participant between arms.
- When the app confirms a connected visible element for the assigned variant, the system shall queue one `wmm_experiment_exposure` event with exact scope properties and a stable event UUID.
- The system shall return `QUEUED_NOT_DELIVERED` after SDK acceptance; unavailable capture, consent withdrawal, identity changes and disabled flags shall reject further event queuing.
- The system shall store only `hashed_identity_namespace` values locally and emit no app conversation, email, name or raw user ID in custom event properties.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Review before installation
  Given a current tracking proposal
  When the operator downloads the `instrumentation_bundle`
  Then the files and their source hashes match the selected experiment
  And no installation or provider success is claimed

Scenario: Unsupported provider setup
  Given local evaluation or bootstrapping is configured
  When the browser module attempts to assign a variant
  Then it returns `SDK_PREREQUISITES_REQUIRED`

Scenario: Stable identity and repeat exposure
  Given a consented identified user and a saved `sticky_assignment`
  And the provider freshly returned the `control` variant
  When the same variant is rendered repeatedly across tabs
  Then `wmm_experiment_exposure` retains one stable event UUID
  And acceptance is reported as `QUEUED_NOT_DELIVERED`

Scenario: Private custom properties
  Given a consented identified participant
  When local assignment state is persisted
  Then only the `hashed_identity_namespace` is stored as the participant key
```

## SHOULD — Operational constraints
Use IndexedDB transactions for cross-tab assignment/acceptance state. Preserve a
stable event UUID across retries; a capture exception or undefined result does
not count as delivery. Fresh flag resolution must precede every assignment or
exposure, so local cache cannot override a provider kill switch. Consent and app
identity are checked again after asynchronous work. The app remains responsible
for consent, provider initialization, identity/reset and its visible renderer.

## SHOULD NOT — Claims and authority
Do not install packages, modify an app repo, initialize secret keys, create flags,
launch experiments, enable analytics without consent or infer human views from
DOM visibility. Native mobile adapters, cross-device deduplication, concurrent
experiment interference controls and a real provider pilot remain separate work.

## Primary integration references
- https://posthog.com/docs/feature-flags/creating-feature-flags#persisting-feature-flags-across-authentication-steps
- https://github.com/PostHog/posthog-js/blob/main/packages/browser/src/posthog-core.ts
- https://posthog.com/docs/libraries/js/usage
