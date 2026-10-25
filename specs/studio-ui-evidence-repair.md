# Spec: studio-ui-evidence-repair
Status: draft

## MUST - Truthful session observations
### Description
Repair presentation and evidence timestamps in the existing Studio inspector.
Preserve the parent studio-control-ui requirements and protected transport.

### Requirements (EARS)
- When close returns CLOSED, the system shall show the confirmed state without old fields or an uncertainty warning through `closed_truth`.
- When controls or attempt history are absent, the system shall show unavailable coverage instead of zero through `missing_evidence`.
- When a report is generated, the system shall return the snapshot receipt UTC timestamp and the export generation UTC timestamp at 1 ms resolution through `snapshot_time`.
- When modal content changes, the system shall set keyboard focus to the new content or the edited setting after saving through `focus_transition`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: closed_truth
  Given a session with editable fields
  When `closed_truth` receives CLOSED
  Then the inspector shows CLOSED without stale fields or an uncertainty warning
Scenario: missing_evidence
  Given a response without controls or attempt history
  When `missing_evidence` renders the inspector and report
  Then absent counts are unavailable and supplied empty collections count zero
Scenario: snapshot_time
  Given a saved session snapshot
  When `snapshot_time` generates a report later
  Then loaded time remains the snapshot receipt time
Scenario: focus_transition
  Given a keyboard user editing a setting
  When `focus_transition` replaces modal content after a successful save
  Then focus returns to the same setting
```
