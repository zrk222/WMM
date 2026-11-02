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
