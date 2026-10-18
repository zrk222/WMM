# Spec: tracking-sequence
Status: approved
SpecFactor-target: 0.75–2.5

## MUST — Functional core

## Goal
Let the marketing agent propose and execute the existing aggregate PostHog tracking
read through the same exact-approved durable campaign sequence as other evidence
actions. Human approval must show the experiment, source, release, locale and
window. No SDK installation, flag mutation, campaign publication or spending.

### Requirements (EARS)
- The system shall return at most 3 `inspect_tracking` options with the full app-owned `tracking_plan` bound into the resolution option hash.
- The system shall store the parent `approved_at` and `expires_at` unchanged in the native tracking child on dispatch or replay, within the original 1800 seconds approval window.
- The system shall store one native tracking child job and its owned `sequence_jobs` membership atomically for each exact approved parent action.
- When the owning sequence is cancelled, the system shall store `CANCELLED` in its active tracking child and reject in-flight provider result adoption.
- When a native tracking child returns `NEEDS_SETUP`, `NEEDS_REVIEW` or `NO_OBSERVATIONS`, the system shall return parent progress `NEEDS_RESOLUTION` without verifying the original requirement.
- If the app, source or `policy_hash` changes, the system shall reject further tracking reads under the previous approval.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Complete one approved tracking action
  Given a current registered experiment and app-owned PostHog source
  And a recommended `inspect_tracking` action
  When the operator approves the exact source-bound sequence action
  Then one durable native tracking child inherits the parent expiry
  And its `approved_at` matches the parent approval
  And its owned `sequence_jobs` membership is committed with the child
  And parent progress waits for the child's verified native receipt

Scenario: Stop during a provider read
  Given an approved tracking child with a request in flight
  When the operator cancels its owning sequence
  Then the child job and receipt are cancelled atomically
  And the native child state is `CANCELLED`
  And no provider result is adopted after cancellation

Scenario: Missing measurement is not success
  Given a provider read job completed without a usable observed tracking result
  And its native receipt reports `NEEDS_SETUP`
  When the parent reconstructs child progress
  Then the action requires resolution and the original requirement stays unverified

Scenario: Source authority changed
  Given an approved tracking action with an older `policy_hash`
  When the operating policy changes before dispatch
  Then the action is rejected before any provider request
```

## Verification
Use isolated synthetic sources and mocked provider responses. Test exact source
derivation, stale plans, replay, inherited expiry, restart, queued/in-flight
cancellation, missing setup and parent result truth. Run all regressions and
hash-bound workflow audit. Actual provider access remains unverified.

## SHOULD — Operational clarity
Show the exact project, source, experiment, release, locale and UTC acquisition
window using the existing review surfaces. Keep native receipt history and
recovery guidance after reload. Do not collect credentials in approval forms.

## COULD — Future work
Supported SDK installation, actual flag launch/pause and a genuine low-risk
assignment/exposure pilot remain separate implementation and approval work.
