# Spec: safe-branch-hygiene
Status: approved

## MUST - Functional core
### Description
Delete only explicitly eligible stale merged agent branches and retain an inspectable pre-deletion manifest.
### Requirements (EARS)
- The system shall reject deletion for protected, open-PR, active-worktree or non-codex branches under `eligibility`.
- The system shall require a main-merged PR with the exact current branch head and both merge and commit age over 7 days under `merge_proof`.
- The system shall store a pre-deletion manifest before enabling any branch deletion under `manifest`.
- The system shall reject deletion when the current head or eligibility changes after the manifest under `recheck`.
- The system shall emit actual deleted, skipped and failed branch outcomes without claiming a branch-count target under `outcomes`.
### Acceptance criteria (Gherkin)
```gherkin
Scenario: eligibility
 Given protected and active candidate branches
 When `eligibility` executes
 Then no ineligible branch is deleted
Scenario: merge_proof
 Given a squash-merged PR and matching branch head older than 7 days
 When `merge_proof` executes
 Then its deletion eligibility is recorded
Scenario: manifest
 Given an eligible deletion plan
 When `manifest` executes
 Then a retained manifest precedes mutation
Scenario: recheck
 Given a changed head or newly open PR
 When `recheck` executes
 Then deletion is rejected
Scenario: outcomes
 Given partial provider failure
 When `outcomes` executes
 Then actual results remain explicit
```

## SHOULD - Technical
Use GitHub APIs and exact refs, no destructive local filesystem cleanup or full-history clone. Scheduled cleanup applies the same guards as manual runs. Explicit dry-run remains available. GitHub ref deletion has no atomic expected-SHA precondition; document residual remote race and do not claim atomic compare-and-delete.
