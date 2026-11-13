# Spec: campaign-monitor-integration
Status: draft

## MUST - Functional core
### Description
Connect the existing finite monitor to the original owner HTTP dispatcher, original campaign policy checker and supervised worker. No monitor scope is created or enabled implicitly.

### Requirements (EARS)
- The system shall route exact owner monitor POST requests through existing session, fresh identity, origin and CSRF checks through `owner_route`.
- The system shall reject monitor actor impersonation or unrelated campaign effects through the original policy checker through `narrow_policy`.
- The system shall enqueue and execute due approved monitor work using Runner.poll without a browser session through `background_run`.
- The system shall store BLOCKED for exact campaign_monitor jobs returning status BLOCKED and reject automatic replay of interrupted or failed monitor work through `failure_state`.
- The system shall return existing protected Page post and paid scheduler behavior unchanged through `regression`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: owner_route
  Given authenticated and anonymous real loopback clients
  When `owner_route` requests finite monitor setup
  Then only the current owner using the exact protected route succeeds
Scenario: narrow_policy
  Given a leased monitor and a forged owner actor
  When `narrow_policy` evaluates provider access
  Then only exact retained monitor reconciliation or approved pause can pass
Scenario: background_run
  Given an approved due monitor and closed owner browser session
  When `background_run` polls the actual worker
  Then exact existing campaign observations and verified protective pause are persisted
Scenario: failure_state
  Given a blocked result or interrupted monitor lease
  When `failure_state` runs and polls again
  Then the job stays BLOCKED and no provider mutation is replayed
Scenario: regression
  Given existing scheduled Page and paid Meta work
  When `regression` runs their guarded worker tests
  Then publication, quota, no-replay and verified pause checks retain their results
```

## SHOULD - Technical
- Add campaign-monitor to the closed owner domain map, narrow retained policy check, supervision components, special worker dispatch and no-reclaim/no-auto-retry paths.
- Only action campaign_monitor with dictionary result status BLOCKED changes the generic normal-return success mapping.
- Existing monitor expiry and existing-intent-only limitations remain; no implicit enrollment or live provider acceptance.


## Retained authority and bounded execution
Before unattended work, check current owner membership/version, app revision/hash, ACTIVE unexpired campaign permission, connection/configuration revisions, connection renewal/expiry, summary integrity and exact target request hashes. Changed authority blocks work; a stored approval flag alone is insufficient.
Queue at most 20 due monitors per tick. Finite run/provider-unit exhaustion becomes BLOCKED. Protective pause uses observations no older than 30 seconds. OFF cancels queued work; it cannot cancel an already dispatched provider mutation or release its held commitment.

## Recovery and confirmation
Expired RUNNING work becomes BLOCKED with MONITOR_INTERRUPTED_UNCONFIRMED and an instruction to inspect saved receipts. Consume the pause attempt before calling the provider. Only PAUSED_campaign is accepted as confirmed success. A lost reply leaves UNKNOWN with commitment held; process death immediately after mutation can retain PENDING_PAUSED_campaign and the same hold. Neither a mutation journal nor BLOCKED job proves provider pause. Reconcile the existing intent through current owner controls; never automatically issue another mutation.

## Acceptance infrastructure and proof boundary
The integration fixture runs a real loopback server and Runner with synthetic owner identity, credentials and FakePaidTransport. The abrupt-exit child writes a synthetic mutation journal and exits with code 73 directly after pause mutation. Its network resolution is denied; a replacement mutation raises instead of succeeding. The restart assertions require one mutation, retained commitment 80, pending/unconfirmed pause state and a blocked interruption. The separate lost-reply case requires UNKNOWN and the same hold. These are reproducible synthetic acceptance tests, not live Meta, paid campaign, or owner-host acceptance.

## Alternatives
Reuse retained narrow authority rather than require an interactive session for every poll: an interactive session would defeat approved unattended work. Retain current checks instead of trusting activation-time facts alone: later revocation must stop work. Block interrupted mutations instead of retrying them: retry could duplicate an external effect. Reconcile exact existing intents rather than releasing holds when a worker stops: a stopped process does not undo remote activity or incurred spend.


### Recovery classification and protected receipt projection
IN_FLIGHT skips protective mutation and can return OBSERVED while future scheduled reconciliation continues. OWNER_UNVERIFIED or LEASE_STATE_CONFLICT raises and blocks the monitor; UNKNOWN without an eligible protective-pause reason also blocks. These differ from expired RUNNING work.
A protective pause requires a saved campaign ID, provider campaign status exactly ACTIVE and observation age from zero through 30 seconds. The configuration_drift rule requires configuration exactly CHANGED_OR_UNCONFIRMED_PAUSE_RECOMMENDED; active_after_end requires the intent end time already passed.
Owner-visible recovery receipts validate the last job app/action, exact monitor ID/hash, bounded version/run and recognized status. Parsed result objects are bounded to 65,536 characters and observations to 20; observations are restricted to retained target IDs and allowlisted status/recovery values. Project only selected fields rather than private provider response or credential payloads.
