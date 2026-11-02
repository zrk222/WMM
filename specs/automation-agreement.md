# Spec: automation-agreement
Status: draft

## MUST - Functional core
### Description
Return one combined owner review of selected existing local-work policy, campaign scope and finite schedule. The read model creates no authority and does not replace any independent execution guard.

### Requirements (EARS)
- The system shall reject selections with extra fields, zero selected resources, foreign owners or stale manifest versions through `selection_boundary`.
- The system shall return selected current app, owner, policy and catalog bindings in one SQLite read transaction through `snapshot`.
- The system shall return existing local policy status and summary hash with distinct local and campaign financial records through `independent_scopes`.
- The system shall return exact scheduled post requests, due times, input hashes, current job states and dispatch uncertainty through `batch_review`.
- The system shall return a matching combined summary digest and authority_issued false over protected HTTP without durable writes, secret resolution or provider effects through `read_only`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: selection_boundary
  Given selected foreign resources, an outdated manifest or an empty selection
  When `selection_boundary` requests an agreement
  Then the request is rejected without returning resource data
Scenario: snapshot
  Given current owner-owned local and campaign resources
  When `snapshot` reads their combined agreement
  Then current app, owner and catalog bindings share one consistent read snapshot
Scenario: independent_scopes
  Given independent finite local-work and campaign approvals
  When `independent_scopes` summarizes them
  Then local zero spend and campaign media ceilings remain distinct and no universal grant is reported
Scenario: batch_review
  Given a saved scheduled post and changed or uncertain job receipt
  When `batch_review` reads the schedule
  Then exact due times and post identities are bound and uncertainty requires reconciliation
Scenario: read_only
  Given private synthetic credential fields and existing durable resources
  When `read_only` reads the agreement over protected HTTP
  Then its summary digest matches and no durable data or authority is created
```

## SHOULD - Technical
- Exact selection fields: manifest_version, workflow_policy_id, campaign_scope_id and schedule_batch_id; at least one of the three resource IDs is non-null.
- The owner is supplied by the existing fresh session adapter, never by body fields.
- Scheduled batches implicitly include their linked campaign as a dependency; an explicitly selected different campaign is rejected.
- Unknown credential price, fees, provider lag, unverified freshness and dispatched uncertainty remain explicit; no provider readback is performed.
