# Spec: automation-agreement-ui
Status: draft

## MUST - Functional core
### Description
Unified owner-facing inspection of existing separately enforced workflow/campaign/schedule authority; this view neither replaces approval nor activates scopes.

### Requirements (EARS)
- The system shall display existing owner workflow policies, campaign scopes and scheduled batches for exact selection through `agreement_select`.
- When the owner submits a selection, the system shall display the `hash-bound combined agreement` without issuing authority through `agreement_read`.
- If app, version, principal or dialog changes, the system shall reject late agreement readback through `agreement_stale`.
- The system shall emit a `sanitized owner report` containing identifiers, status and approved resource allowances without private copy or credentials through `agreement_report`.
- The system shall display the `Per-campaign media cap` and `Maximum total media commitment` as distinct labeled fields with currency through `agreement_read` and `agreement_report`.
- The system shall display the `Exact approved content, rights and targeting hashes` in the agreement and owner report without exposing private content or rights prose through `agreement_read` and `agreement_report`.
- The owner-only schedule review shall show the exact saved organic post link as text, or show that no link was approved. The exported report shall exclude the link.
- Before activating a draft organic campaign, the owner-only combined agreement shall show the proposed copy and full link as text when the content and rights hashes match the saved draft. It shall display the selected Meta request ceiling. Preview shall neither activate the scope nor contact Meta. Export shall exclude the draft copy and link.
- If a local-work policy is selected, the system shall display exactly its agent, permitted operations, saved ISO-8601 expiry timestamp, integer calls-used count, configured integer call allowance (1 through 10000 calls), and `spend_limit_minor` as a fixed 0 minor currency units in the sanitized owner report through `agreement_report`; unavailable fields shall be labeled and private payloads and credentials shall remain excluded.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: agreement_select
 Given an authenticated app owner
 When `agreement_select` checks the current selection
 Then every selected family remains visible
Scenario: agreement_read
 Given an exact current selection
 When `agreement_read` checks the current selection
 Then the `hash-bound combined agreement` is displayed without activating any policy or campaign
Scenario: agreement_stale
 Given a changed workspace during read
 When `agreement_stale` checks the current selection
 Then the previous response does not replace current UI
Scenario: agreement_report
 Given a displayed agreement
 When `agreement_report` checks the current selection
 Then the `sanitized owner report` contains no post copy or secrets
Scenario: agreement_campaign_limits
 Given a campaign scope with per-campaign and total media ceilings
 When `agreement_read` checks the current selection
 Then the `Per-campaign media cap` and `Maximum total media commitment` each display their own approved amount and currency
Scenario: agreement_approved_fingerprints
 Given a campaign scope with approved content, rights and targeting hashes
 When `agreement_read` checks the current selection
 Then the `Exact approved content, rights and targeting hashes` are visible in the agreement and owner report
 And raw content, rights prose and credentials remain excluded
Scenario: agreement_local_work_report
 Given a selected local-work policy with an agent, operation allowlist, expiry, call usage and zero spend
 When `agreement_report` checks the current selection
 Then the report lists those exact local-work limits and labels unavailable values
 And private policy payloads and credentials remain excluded
```

## Authorized parameters
Synthetic review fixtures use these existing saved scope values; this UI cannot set authority.
max_total_minor = 100
max_posts = 1
max_campaigns = 1
max_calls = 50
