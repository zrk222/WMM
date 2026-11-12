# Spec: auto-enrolling-ratchets
Status: approved

## MUST - Functional core
### Description
Automatically enroll changed source in the existing format, lint and type ratchets.
### User roles
- Contributors and CI reviewers
### Requirements (EARS)
- The system shall reject absent enrollment for every added or modified Python and JavaScript source in the corresponding maintained registry under `changed_enrollment`.
- The system shall reject removal of existing registry entries while retaining deleted-file history under `append_only`.
- The system shall emit differences between the reviewed base and candidate Git trees without executing either tree under `explicit_base`.
- The system shall store changed paths through an explicit deterministic enrollment command under `automatic_update`.
- The system shall fail CI with actionable missing enrollment and retain reproducible negative tests under `failure_evidence`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: changed_enrollment
 Given a repository source change
 When `changed_enrollment` checks the candidate
 Then its declared invariant is verified and violations fail
Scenario: append_only
 Given a repository source change
 When `append_only` checks the candidate
 Then its declared invariant is verified and violations fail
Scenario: explicit_base
 Given a repository source change
 When `explicit_base` checks the candidate
 Then its declared invariant is verified and violations fail
Scenario: automatic_update
 Given a repository source change
 When `automatic_update` checks the candidate
 Then its declared invariant is verified and violations fail
Scenario: failure_evidence
 Given a repository source change
 When `failure_evidence` checks the candidate
 Then its declared invariant is verified and violations fail
```

## SHOULD - Technical
Use Git object reads and null-delimited paths; never modify source while checking. New source enrollment must run the existing checks. No provider effects.
