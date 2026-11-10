# Spec: instrumentation-lifecycle

Status: draft

## MUST - Functional core
### Description
Track the browser integration package lifecycle separately from delivery and
business outcomes: generated/downloaded, owner-reported installation and
owner-reported live probe. Each step is an immutable app-owned receipt. None of
them launches an experiment, verifies provider delivery or proves a business result.

### Requirements (EARS)
- The system shall retain an immutable `instrumentation_receipts` record binding app, experiment, proposal hash, bundle hash, state, previous receipt, data, hash and creation time through `instrumentation_receipts`.
- The system shall use the closed states `DOWNLOADED`, `REPORTED_INSTALLED` and `PROBE_OBSERVED`.
- When the exact integration package is downloaded, the system shall retain one idempotent `DOWNLOADED` receipt for that app, experiment, proposal and bundle.
- The system shall require a fresh identity and current app owner membership inside the write transaction for installation and probe receipts. It shall bind the actor and role version to each new attestation. Existing receipts without this evidence remain historical and cannot advance verified owner lifecycle progress.
- When the owner reports installation, the system shall require the exact prior download receipt and hash, current app release, a bounded installation reference and a nonfuture report time, and shall append one idempotent `REPORTED_INSTALLED` receipt.
- When the operator records a live probe, the system shall require the exact prior installation receipt and hash, current app release, uppercase provider token, bounded event identity, nonfuture observed time at or after installation, bounded scope and a lowercase source-receipt SHA-256, and shall append one idempotent `PROBE_OBSERVED` receipt.
- The system shall reject foreign, out-of-order, mismatched, malformed or extra-field lifecycle requests without writing.
- The system shall return per experiment the separate state results, receipt identities and hashes, and fixed next actions, and shall state that download is not installation, attestation is not verified delivery and a probe is owner-reported.
- The system shall expose the readout in the workspace and render it in the tracking review with controls to report installation or a live probe.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: instrumentation_lifecycle_order
  Given a downloaded integration bundle
  When the operator reports installation and then a live probe
  Then each receipt references the exact previous receipt and hash
  And a later stage is never inferred from an earlier one
Scenario: instrumentation_lifecycle_idempotence
  Given an exact lifecycle payload
  When it is submitted twice
  Then the retained receipt is returned once
Scenario: instrumentation_lifecycle_rejection
  Given stale, foreign, future-dated, malformed or extra-field input
  When lifecycle recording is attempted
  Then no receipt is written
Scenario: instrumentation_lifecycle_boundary
  Given saved lifecycle receipts
  When the workspace readout renders
  Then download, installation and probe remain separate
  And provider delivery and business outcomes remain unproven
```
