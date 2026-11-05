# Spec: weekly-review-actions
Status: approved

## MUST - Functional core
### Description
Extend the existing weekly exception inbox with bounded app-member agent-review metadata and links to existing exact review controls. No approval, retry or provider effect occurs from reading or opening an exception.

### Requirements (EARS)
- When a signed-in current OWNER or CHECKER reviews an app, the system shall return actionable agent-review cards through `review_visibility`; an active MAKER shall receive only their own requests and anonymous or revoked members shall receive 0 private cards.
- The system shall return at most 100 request metadata rows per app within the existing 5-app weekly page through `bounded_metadata`, excluding raw envelopes, results, credentials and tokens.
- When a checkpoint waits for review or has unresolved UNKNOWN or CANCEL_REQUESTED state, the system shall return one stable source-bound card through `review_state`; unchanged valid APPROVED/RUNNING and terminal completed/cancelled states shall return 0 cards.
- If pending authority expires or app, maker/checker role or grant context changes, the system shall return a recovery reason through `stale_authority`, with 0 seconds of grace after expiry and no assertion that an in-flight effect stopped.
- If a private request source cannot be verified, the system shall return a redacted source exception through `source_failure`; review cards shall not require campaign_scopes to exist.
- When a user opens an agent-review card, the system shall return the current selected app and exact request inspection through `recovery_route` using existing independent-review controls and 0 automatic approvals or effect retries.
- If the signed-in principal changes, the system shall return 0 cached private cards and 0 prior-principal private analytics/report counts through `cached_privacy` until a matching fresh review is loaded.
- When the existing checkpoint is cancelled or reconciled, the system shall remove the resolved card on refresh through `resolution` without deleting its receipt or adding a second dismissal/authority store.
- The system shall display the review and recovery workflow at 1440px and 390px with keyboard access and existing JSON/PDF reporting through `gui_review`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: review_visibility
 Given OWNER MAKER CHECKER and revoked or anonymous identities
 When `review_visibility` reads real temporary app roles
 Then only assigned metadata is returned and no approval authority is granted
Scenario: bounded_metadata
 Given more than100 retained requests with private raw input
 When `bounded_metadata` projects a5app page
 Then at most100request rows per app are inspected and no raw input or result appears
Scenario: review_state
 Given waiting uncertain and terminal checkpoint states
 When `review_state` refreshes the inbox
 Then stable source-bound cards describe actionable work only
Scenario: stale_authority
 Given an expired grant changed app or revoked maker
 When `stale_authority` evaluates pending work
 Then a recovery reason appears and unresolved effects remain unresolved
Scenario: source_failure
 Given missing campaign_scopes or damaged request metadata
 When `source_failure` evaluates reviews
 Then review cards remain independent and damaged sources produce redacted exceptions
Scenario: recovery_route
 Given a visible exact request card
 When `recovery_route` opens it
 Then existing review controls recheck current permissions before any decision
Scenario: cached_privacy
 Given a response for principalA followed by principalB or signout
 When `cached_privacy` renders cards and reports
 Then principalA private metadata and counts are absent
Scenario: resolution
 Given a waiting or uncertain request
 When `resolution` observes cancellation or reconciliation
 Then the active card disappears and original history remains
Scenario: gui_review
 Given desktop1440px and mobile390px
 When `gui_review` uses keyboard recovery and exports
 Then the exact request is inspectable and no automatic approval occurs
```

## SHOULD - Technical/structural
Reuse weekly_inbox, existing checkpoint/grant validation, current roles, WMMAgentControl and WMMPageReports. New cards use category/resolution_route agent_review, priority1, action.resource_id exact request ID, private_principal current session principal, and owner_only false. The weekly response's existing owner_operations_principal is the trusted request principal; both cards and report counters must compare it with the current principal. State projection is metadata only, not approval validation. Preserve existing owner-only delivery/monitor/report/handoff cards, existing pagination, and all 12 advanced stages. No new queue, role, endpoint, credential or authority store.

When grant ownership cannot be established, an active app member may receive one generic app-level review-source health card, independent of damaged request count. This card contains no affected request/grant identifiers, packet hashes, ownership attribution or request-derived timestamps. MAKER visibility over individual requests still requires verified saved grant ownership; valid foreign requests remain omitted. Anonymous and revoked members receive no private source-health cards.
