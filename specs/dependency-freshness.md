# Spec: dependency-freshness
Status: approved

## MUST - Functional core
### Description
Schedule dependency vulnerability checks and reviewed update proposals without loosening exact pins or hashes.
### Requirements (EARS)
- The system shall reject runtime dependency installation without exact versions and required hashes under `locked_audit`.
- The system shall emit weekly grouped update PRs for Python, JavaScript and action dependencies without automatic merge under `update_proposals`.
- The system shall reject FFmpeg updates without an official release asset SHA256 and a matching versioned URL under `binary_pin`.
- The system shall preserve unrelated workflow content and reject an unreviewed baseline when updating the FFmpeg version under `baseline`.
- The system shall store advisory and update receipts and fail required checks on audit or update errors under `audit_results`.
### Acceptance criteria (Gherkin)
```gherkin
Scenario: locked_audit
 Given hash-locked runtime and audit requirements
 When `locked_audit` executes
 Then incomplete pins are rejected
Scenario: update_proposals
 Given a weekly dependency schedule
 When `update_proposals` executes
 Then changes are proposed for review without auto-merge
Scenario: binary_pin
 Given an official release metadata response
 When `binary_pin` executes
 Then only exact versioned asset and SHA256 updates are prepared
Scenario: baseline
 Given unrelated workflow drift
 When `baseline` executes
 Then the update is rejected without changing source
Scenario: audit_results
 Given missing provider evidence or vulnerability-service failure
 When `audit_results` executes
 Then a retained non-pass receipt accompanies the failed check
```

## SHOULD - Technical
Use native Dependabot for pip, npm and GitHub action updates, a hash-locked pip-audit tool profile and npm audit, and a small FFmpeg metadata updater. No binary downloads for freshness metadata. FFmpeg proposals use a new branch and trigger the standard check workflow through explicit workflow_dispatch; GITHUB_TOKEN-created PRs cannot be assumed to trigger CI. No provider credentials in logs, no auto-merge, no deployments or spending.
