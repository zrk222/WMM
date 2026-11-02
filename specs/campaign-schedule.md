# Spec: campaign-schedule
Status: draft

## MUST - Functional core
### Description
Schedule a finite owner-approved batch of exact Facebook Page posts through existing campaign execution. Paid advertising is outside this slice.

### Requirements (EARS)
- The system shall bind a batch of at most 20 exact posts and due times to an active owner-approved campaign scope through `batch_binding`.
- When a due post is claimed, the system shall atomically create one durable job with its exact request identity through `atomic_dispatch`.
- When a worker executes a post, the system shall revalidate the retained batch, current scope, owner, app and connection at each effect boundary through `effect_authority`.
- If a worker loses its lease after dispatch, the system shall block automatic mutation replay and retain the campaign intent through `unknown_recovery`.
- When the owner switches a batch OFF, the system shall cancel unclaimed work and block future effect admissions through `off_control`.
- The system shall expose saved scheduling and provider receipt states without credentials or network requests through `status_read`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: batch_binding
  Given a current owner and active campaign scope
  When `batch_binding` reviews an exact post batch
  Then changed content, scope or due time cannot activate the reviewed batch
Scenario: atomic_dispatch
  Given one due post and two schedulers
  When `atomic_dispatch` claims the post
  Then exactly one durable job is created
Scenario: effect_authority
  Given a scheduled post with changed owner, app or connection
  When `effect_authority` checks the provider boundary
  Then no provider mutation is admitted
Scenario: unknown_recovery
  Given a worker interruption after dispatch
  When `unknown_recovery` observes the expired lease
  Then no automatic mutation replay occurs
Scenario: off_control
  Given an active batch and an unclaimed post
  When `off_control` switches the batch OFF
  Then future dispatch is blocked and the queued job is cancelled
Scenario: status_read
  Given an owner and a saved batch
  When `status_read` returns the batch
  Then it distinguishes queued and provider receipt states without returning credentials
```

## SHOULD - Technical
- Reuse campaign execution scope checks, durable post intents and pinned transport.
- No database writer transaction may span network access.
- Approval expiry remains at most 24 hours and paid scheduling is unsupported.
- Live provider acceptance is NOT_RUN.

## Authorized parameters
MAX_ITEMS = 20
MAX_HOURS = 24
MAX_DUE_PER_TICK = 20
