# Spec: campaign-sequence
Status: approved
SpecFactor-target: 0.75–2.5

## MUST — Functional core
### Description
Mission Control recommends an ordered sequence of available evidence actions for the selected app. The operator reviews and optionally removes actions, then approves the exact sequence. The local worker follows that sequence without requiring an open browser, retains outcomes and resumes from saved state after restart. This executor uses existing read-only evidence tools; the full campaign and live experiment adapters remain separate implementation requirements.

### User roles
- Local operator: approve, edit the selected action list, inspect results or cancel.
- Local worker: execute only the reviewed source-bound action list.

### Requirements (EARS)
- The system shall return `proposal_hash` for exactly the current unique ready evidence actions derived from app-owned resolution options, excluding redundant fresh website reads when a current saved observation exists.
- When the operator approves `selected_steps`, the system shall store exactly those actions in their reviewed order with current app, record, policy and target hashes and the existing approval window.
- When an approval `request_key` is replayed, the system shall return exactly the existing saved sequence without extending its approval or duplicating work.
- The system shall store `checkpoint` after each terminal child outcome before dispatching the next action, and shall resume exactly that saved position after restart.
- When the operator cancels, the system shall use `sequence_jobs` ownership to cancel queued owned work, reject adoption of in-flight owned results, and leave preexisting shared reads unchanged.
- If the app, policy, evidence records or `expires_at` authority changes, the system shall reject exactly the remaining owned execution before and after tool calls and return an approval-required explanation.
- When an action fails, the system shall store `step_outcomes` and continue only the independently approved remaining actions; missing receipts and unverified results shall not become campaign success.
- The system shall return `next_actions` at completion or interruption, including evidence review, current resolution alternatives or a new sequence proposal; no original requirement shall be automatically verified.
- The system shall report `execution_mode` as LOCAL_SERVICE_REQUIRED and persist progress across browser closure and service restart without a new external schedule.
- The system shall retain `spend_minor` as exactly zero and reject arbitrary commands, client envelopes, unregistered tools and generic queue bypasses.
- The system shall render `sequence-dialog` with action selection, approval scope, readable per-action progress, keyboard dismissal, cancellation and recovery controls on desktop and mobile.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Review current work
  Given an app with ready evidence actions
  When the operator opens the plan
  Then `proposal_hash` binds the displayed choices
  And `sequence-dialog` permits reviewing and excluding choices

Scenario: Approval and replay
  Given a reviewed source-bound proposal
  When the operator approves `selected_steps`
  Then `request_key` identifies the saved sequence on replay
  And `spend_minor` remains zero

Scenario: Restart and failure
  Given a completed child and a later failed child
  When the local service resumes
  Then `checkpoint` prevents duplicate execution
  And `step_outcomes` retains the failure
  And `execution_mode` remains LOCAL_SERVICE_REQUIRED

Scenario: Cancellation and changed authority
  Given an active sequence with owned and shared reads
  When the operator cancels or the saved authority changes
  Then `sequence_jobs` preserves shared reads and stops owned work
  And `expires_at` prevents further expired execution
  And `next_actions` explains current approval or evidence review
```

## SHOULD — Technical/structural
- Existing durable jobs execute each fixed resolution; a separate app-scoped coordinator stores the reviewed plan and progress. Child request identities are deterministic per sequence and position.
- Source jobs created during a sequence are linked inside the same transaction as enqueue. Preexisting jobs are linked as shared observations. A cancellation cannot race a newly committed unlinked source job.
- A read already in flight may finish remotely; cancellation prevents result adoption and additional owned reads. Evidence already recorded remains retained.
- Tool observations use closed states, summaries, artifact references and recovery steps. Raw provider diagnostics are not added to model context by this feature.
- Existing provider read quotas, worker leases, retry rules and per-resolution expiry remain enforced. The action list is finite and determined by current registered options rather than an invented autonomous iteration budget.

## SHOULD NOT — Implementation details
- No campaign publication, ad spending, new provider grant, automatic model inference or claim of causal lift is introduced by this executor.
- No existing operational data, credential, unrelated edit or previous receipt is deleted.

## Decision logic (factory candidates)
| # | if | then |
|---|----|------|
| 1 | `checkpoint` references an active child | wait for its durable outcome |
| 2 | `step_outcomes` records a terminal failure | retain the failure and advance to the next independently approved action |
| 3 | `expires_at` authority changes | stop and request current approval |
