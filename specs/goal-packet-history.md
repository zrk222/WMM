# Spec: goal-packet-history
Status: approved

## MUST - Functional core
### Description
Persist one selected goal draft through existing pipeline jobs and reopen its dated source snapshot after restart. Saving is local preparation; no approval, provider effect or business outcome is granted.

### Requirements (EARS)
- When Save packet is selected for research, creative, campaign or measurement, the system shall validate goal, positive manifest_version and 64-character lowercase source_hash through `save_packet` before queueing existing pipeline stage 0.
- If the app version or source hash changes before preparation, the system shall reject the saved packet output through `stale_source` with 0 provider calls and 0 automatic retries.
- When the same app, goal and source snapshot are saved again, the system shall return the existing request identity through `deduplicate`.
- When a stored packet is reopened after runtime restart, the system shall return its saved job ID, creation date, app version, source hash and fixed goal stage subset through `reopen`.
- If current app evidence differs from a retained packet, the system shall return a historical packet label through `history_state`; queued, failed and absent outputs shall not appear as completed packets.
- The system shall show at most 5 selected-goal saved runs from the existing app-scoped 100-job window through `bounded_history` and escape source text.
- The system shall offer keyboard-accessible save, refresh, reopen, JSON and PDF controls at 1440px and 390px through `gui_packet`.
- The system shall return all 12 advanced stages and external_execution NOT_RUN with spend_minor 0 through `authority`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: save_packet
 Given one selected goal and matching app version and 64-character source hash
 When `save_packet` validates the request
 Then pipeline stage 0 is queued with local draft metadata only
Scenario: stale_source
 Given app evidence changes before worker preparation
 When `stale_source` checks expected bindings
 Then packet output is rejected with no provider call
Scenario: deduplicate
 Given the same app goal and source snapshot
 When `deduplicate` admits two explicit save requests
 Then both return the same job ID
Scenario: reopen
 Given a completed local packet and a restarted runtime
 When `reopen` reads the app-scoped saved job
 Then its original job ID source hash creation date and goal subset are retained
Scenario: history_state
 Given a saved packet and changed current evidence
 When `history_state` opens that packet
 Then historical context is visible and no current completion is implied
Scenario: bounded_history
 Given 6 saved runs in the existing 100-job window
 When `bounded_history` renders selected goal history
 Then at most 5 matching app and goal rows appear with escaped text
Scenario: gui_packet
 Given a viewport of 1440px or 390px
 When `gui_packet` saves reopens refreshes or exports using the keyboard
 Then the current local draft and saved history remain distinct
Scenario: authority
 Given a saved goal packet
 When `authority` inspects the result
 Then all 12 advanced stages remain reachable and external execution is NOT_RUN with spending 0
```

## SHOULD - Technical/structural
Reuse Service.queue, pipeline.prepare, existing worker leases/jobs and page reports. Use fixed stage subsets research 5/6, creative 6, campaign 7 and measurement 3/4/10/11. Do not create another queue, catalog operation or credential store. Preserve anonymous local preparation policy; this feature grants no new sensitive read or effect access.
