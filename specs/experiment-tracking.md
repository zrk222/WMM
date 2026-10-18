# Spec: experiment-tracking
Status: approved
SpecFactor-target: 0.75–2.5

## MUST — Functional core
### Description
Collect app-scoped PostHog experiment configuration and privacy-preserving tracking observations through an existing protected analytics connection. Recommend the expected flag setup from the immutable registered experiment. A queued, explicitly approved read produces durable evidence and recovery steps. This integration is a prerequisite for supported live execution, not a campaign-launch or causal-lift claim.

### User roles
- Local operator: inspect recommended setup, approve exact reads, inspect evidence or stop pending work.
- Local worker: perform only fixed provider reads within current app/source/experiment authority.

### Requirements (EARS)
- The system shall derive `flag_key` and expected two-arm configuration from the selected immutable experiment, current app release and owned PostHog source without provider writes.
- When the operator approves, the system shall bind `proposal_hash` to current app, experiment, source configuration and the existing resolution approval window.
- When approval `request_key` is replayed, the system shall return exactly the saved run without duplicating jobs or extending authority.
- The system shall store `tracking_run_id` across worker restart and return queued, reading, terminal and recovery states in app-scoped history.
- If app, source, experiment or protected binding changes, or `expires_at` is exceeded after the existing 1800 seconds approval window, the system shall reject further reads and adoption of stale results.
- When a read finishes, the system shall retain `observed_counts` only for the exact experiment hash, release, locale and declared acquisition window; raw subjects and event properties shall not be persisted.
- The system shall report `flag_findings` for absent, inactive or mismatched provider configuration rather than treating a saved local definition as delivered variants.
- The system shall return `scope` as tracking observation only; assignment evaluation shall not become rendered exposure, business conversion or causal success.
- When the operator confirms `cancel_run`, the system shall stop owned queued work and reject in-flight adoption while preserving previous receipts.
- If setup or tracking is missing, the system shall return `next_actions` naming source access, expected provider setup or app instrumentation and a current review path.
- The system shall render `tracking-dialog` with recommended setup, optional source selection, approve/read controls, per-run state, cancellation, evidence and recovery on desktop and mobile.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Approve current provider reads
  Given a registered experiment and app-owned analytics source
  When the operator reviews `flag_key` and approves `proposal_hash`
  Then `request_key` identifies exactly one `tracking_run_id`

Scenario: Read and distinguish evidence
  Given current approved authority before `expires_at`
  When provider reads return valid scoped aggregates
  Then `observed_counts` contains no subject identifiers
  And `flag_findings` reports configuration mismatches
  And `scope` does not claim causal success

Scenario: Stop or recover
  Given a pending read or unavailable setup
  When the operator confirms `cancel_run` or inspects `tracking-dialog`
  Then `next_actions` explains current review and setup choices
```

## SHOULD — Technical/structural
- Reuse the current fixed-region, no-redirect analytics transport and app-bound Windows credential namespace.
- Persist immutable approval and terminal result hashes with app-owned job identities. Explicit stop does not rewrite old evidence.
- Query counts only. Raw subjects remain inside the provider; missing rows and immature windows are explicit limits. Existing descriptive cohort analysis is unchanged.
- Read calls use existing transport timeout and size bounds. No new dependency, external schedule, credential grant or provider mutation is authorized by this feature.
- Provider requests retain the existing 15 seconds timeout and 2 MB response cap. Query text values retain the existing 200 characters label bound; identifiers retain the existing 120 characters request-identity bound. Flag lookup requests two entries to detect an ambiguous result, and accepts at most one exact key. Existing worker lease recovery permits three attempts; interrupted read-only requests may repeat within that bound, never extend approval or mutate the provider.
- The provider flag lookup uses `limit = 2` entries to detect duplicate exact keys; a second match is a validation error, not a selected campaign.

### Authorized parameters
- limit = 2

## SHOULD NOT — Implementation details
- Do not claim SDK installation, genuine rendered exposure, experiment launch, verified randomization, causal lift or complete autonomous A/B operation from these observations.
- Do not modify owner app profiles or treat synthetic tests as a genuine pilot.

## Decision logic (factory candidates)
| # | if | then |
|---|----|------|
| 1 | `flag_findings` identifies missing provider setup | retain the finding and recommend setup before instrumentation |
| 2 | `observed_counts` has no exposure rows | report missing exposure instrumentation |
| 3 | `expires_at` is no longer current | request current approval before any further read |
