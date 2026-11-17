# Spec: process-status-colors
Status: draft

## MUST - Functional core
### Requirements (EARS)
- When a worker or job status is displayed, the system shall retain its named text and show a state-colored marker through `status_semantics`.
- When the worker or job status is RUNNING, the system shall display a blue badge through `running_state`.
- When the job status is QUEUED, WAITING_FOR_REPORTS or WAITING_REVIEW, the system shall display an amber badge through `waiting_state`.
- When the job status is SUCCEEDED, the system shall display a green badge through `success_state`.
- When the job status is FAILED, the system shall display a red badge through `failure_state`.
- When the worker or job status is STOPPED, PAUSED or CANCELLED, the system shall display a gray badge through `stopped_state`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: status_semantics
 Given saved workflow states and an unrecognized state
 When the shared status helper renders
 Then each named label remains readable and the unrecognized state is neutral
Scenario: running_state
 Given a running worker and an active permission scope
 When their status labels render
 Then blue identifies active work or permission without claiming successful delivery
Scenario: waiting_state
 Given queued work and a completed read waiting for reports
 When their status labels render
 Then amber identifies waiting without claiming metrics are available
Scenario: success_state
 Given a saved succeeded job
 When its status label renders
 Then its named state is green
Scenario: failure_state
 Given a failed job and a blocked job
 When their status labels render
 Then failed is red and blocked is amber
Scenario: stopped_state
 Given stopped, paused and cancelled work
 When their status labels render
 Then muted states distinguish them from running work
```

### Growth Review and report labels

- In Results → Growth Review, evidence availability, review history, journeys and
  experiment review states use the report badge renderer and retain their text.
- Blue means local evidence is recorded or under evaluation. Amber means evidence,
  provider acceptance or a review decision is still needed. A saved listing that
  is ready for review is amber; it does not establish approval or growth.
- Keep the recorded source, reason and app scope visible. Treat unfamiliar labels
  as neutral; never infer meaning from a substring.

## SHOULD - Technical
- Preserve stored process states and approval authority.
- Keep state labels readable at mobile widths and with reduced motion.
- Maintain text contrast of 4.5 to 1 against each state background.
