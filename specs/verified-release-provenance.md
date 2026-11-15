# Spec: verified-release-provenance
Status: approved

## MUST - Functional core
### Description
Require release asset attestations to verify against the exact repository, workflow and source commit before publishing Preview 10.
### Requirements (EARS)
- The system shall reject publication when any staged asset fails provenance verification under `asset_provenance`.
- The system shall reject mismatched repository, signer workflow or source digest in each verification under `source_binding`.
- The system shall emit buyer commands that verify downloaded asset provenance without implying installer signing under `buyer_verification`.
### Acceptance criteria (Gherkin)
```gherkin
Scenario: asset_provenance
 Given an attested staged asset
 When `asset_provenance` executes
 Then verification precedes publication and failures stop the job
Scenario: source_binding
 Given mismatched source or signer evidence
 When `source_binding` executes
 Then the verification command rejects it
Scenario: buyer_verification
 Given downloaded release assets
 When `buyer_verification` executes
 Then the exact provenance verification steps and limits are documented
```

## SHOULD - Technical
Reuse the existing pinned attest-build-provenance action, official gh verification and immutable release publisher. No binary signing or reproducible-build claim. Package production stays hosted; no local desktop builds.
