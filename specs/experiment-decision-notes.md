# Spec: experiment-decision-notes

Status: draft

## MUST - Functional core
### Description
Let the operator attach one bounded human note to a registered experiment. The
note is durable history beside the existing exposure, assessment and decision
records. It grants no approval, never becomes provider verification and never
changes the experiment state.

### Requirements (EARS)
- The system shall accept an experiment action `note` with exactly `operation`, integer `version` and one bounded `note` of 1 through 2000 characters through `experiment_note`.
- When the note is accepted, the system shall append it to the immutable experiment actions, increment the experiment version and preserve the current lifecycle state.
- The system shall not record an assessment, decision, exposure or external effect from a note.
- When the exact note payload is replayed, the system shall return the retained action without a second write.
- The system shall display the note in the experiment decision history labelled as a human note that is not provider verification.
- If the experiment is cancelled or the version changed, the system shall reject the note without writing.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: experiment_note
  Given a planned, observed or evaluated experiment
  When the operator records a bounded note with the current version
  Then the note appears once in immutable action history
  And the lifecycle state, assessments and decisions are unchanged
Scenario: experiment_note_replay_and_rejection
  Given a recorded note and a cancelled or moved experiment version
  When the same payload is replayed
  Then the retained action is returned without a second write
  And a stale, empty, oversized or extra-field note is rejected
```
