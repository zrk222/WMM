# Spec: ci-current-candidate
Status: draft

## MUST - Functional core
### Description
Preserve all existing test jobs while avoiding duplicate feature push/PR runs and cancelling obsolete candidates for the same PR.

### Requirements (EARS)
- The system shall run full local application checks for every pull request and main push through `one_candidate_run`.
- When a newer candidate starts for the same PR, the system shall cancel superseded local/native/package checks through `latest_candidate`.
- The system shall preserve existing platform matrices and test commands through `checks_preserved`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: one_candidate_run
 Given a feature PR update
 When `one_candidate_run` routes the event
 Then one PR workflow and no duplicate feature-push workflow is triggered
Scenario: latest_candidate
 Given two revisions for one PR
 When `latest_candidate` starts
 Then only the newest revision remains running for that workflow
Scenario: checks_preserved
 Given the Windows Ubuntu and iPhone iPad checks
 When `checks_preserved` inspects the workflow jobs
 Then all existing test and package commands remain
```
