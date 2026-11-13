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
- Required selection fields: manifest_version, workflow_policy_id, campaign_scope_id and schedule_batch_id; at least one of the three resource IDs is non-null.
- The owner is supplied by the existing fresh session adapter, never by body fields.
- Scheduled batches implicitly include their linked campaign as a dependency; an explicitly selected different campaign is rejected.
- Unknown credential price, fees, provider lag, unverified freshness and dispatched uncertainty remain explicit; no provider readback is performed.


## Supported draft review and owner-facing output
- Optional `draft_posts` contains 1-20 exact post_data-validated posts. It requires an explicit campaign_scope_id and no schedule_batch_id. The selected campaign must be DRAFT and organic, posts must fit its max_posts and saved approved content/rights hashes. Changed copy, link or rights rejects the request. The response returns draft posts for private review, not in its selection reference list.
- The campaign review includes saved account/destination, approval fingerprints, permission expiry, blockers, receipts and held media commitment. Local-work identity, allowed operations, expiry, used/remaining calls and zero local spend remain separate. Per-campaign media ceilings and total commitments are not inference prices or fees.
- Batch review uses captured admission expiry and current campaign permission. Selected manifest mismatch, foreign ownership identity, invalid resource summary integrity or mismatched selected campaign rejects the review. Saved app or owner revision changes instead appear as current blockers, as do inactive permission or uncertain dispatch; callers must distinguish a rejected selection from a valid blocked review.
- The combined response includes stop rules for OFF/revocation, expiry/source or resource changes, exhausted allowances/ceilings, and uncertain dispatch requiring reconciliation. Each underlying scope keeps its own OFF control. Dispatched effects and incurred charges remain recorded.
- A matching review digest is neither execution authority nor fresh provider verification. New creative variants need their own exact content/rights approval and current downstream authority; this read model cannot approve them.

### Additional acceptance
Given an exact saved draft organic scope, reviewing matching draft posts returns their text/link privately without activation, jobs or writes; a changed link or rights hash rejects.
Given local-work and campaign scope selections, the returned owner summary keeps identities, accounts, expiry, call usage and per-campaign versus total media limits distinct and includes the stop rules.
Given uncertain dispatch, the combined result is blocked and directs reconciliation; it never offers retry authority or releases incurred commitments.

## Design choice and limits
Compose a read-only snapshot of independent scopes rather than issuing a new universal grant: a universal grant would widen authority and duplicate downstream checks. Do not collapse local inference uncertainty into a paid-media cap or treat cached credentials as live provider permission. Returning separate invalid-input errors, blocked current authority and uncertain provider results preserves the operator's next action. This specification describes current projection behavior; live execution and independent user acceptance require their own receipts.


### Paid schedule projection
Saved schedule requests support campaign.publish (validated post_data) and campaign.ad-launch. Paid request keys are exactly request_id, post_id, content_hash, rights_hash, targeting_hash, lifetime_budget_minor, end_time, targeting and name. Validate request identity, hashes, country targeting and integer budget 1-100000000, then call the existing check_paid_review guard with captured permission expiry and scheduled due time. This is historical review: an old end time is not rejected merely because it is now past; current dispatch remains separately guarded. Linked jobs must be campaign_ad or campaign_post as appropriate, in the same app, with exact batch/item/scope/request binding. Mismatched linkage rejects.
