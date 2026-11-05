# Spec: authority-expiry-extension
Status: reviewed design; implementation pending

## MUST - Functional core
### Description
Each authorized app owner can choose a finite permission expiry beyond 24 hours for agent access and standing automation/campaign/organic production approvals. Keep the 24-hour default. Cover new approvals and expiry-only extension of active authority. Reuse current owner authentication, exact review, accounting and execution guards.

### Requirements (EARS)
- When expiry is within 24 hours, the system shall return the existing approval result through `default_lifetime`, with extended consent omitted by default.
- When expiry exceeds 24 hours, the system shall require explicitly true owner consent in the reviewed body through `extended_lifetime`, accept only a representable finite future timestamp, and impose 0 new business-duration ceilings.
- When an owner previews an extension, the system shall return the bound authority ID, immutable scope/version/hash, current owner membership version, consent revision, old/new dates, unchanged lifetime allowances/usage and dependent deadlines through `extension_preview`, with 0 seconds of expiry grace.
- When a current owner confirms that preview, the system shall append an idempotent immutable expiry receipt through `extension_confirm`, checking after writer-lock acquisition that current time precedes the old expiry and the new expiry exceeds it.
- If authority is expired, revoked, changed, uncertain or concurrently amended, the system shall reject extension through `extension_conflict` with 0 seconds of expiry grace and commit no permission or accounting changes.
- The system shall preserve IDs, token hashes, used/reserved calls, posts, generations, held/spent commitments, request keys and lifetime ceilings through `accounting`, with 0 quota resets or provider effects from extending time.
- When linked standing automation and its grant are extended, the system shall commit their consent atomically through `automation_bundle`, preserving their original accounting lineage.
- When execution checks authority, the system shall resolve only a valid contiguous consent chain through `runtime_authority`, retaining all current app, membership, account/config, content, rights, targeting, revocation, quota and uncertainty guards.
- The system shall return original child packet deadlines and proofs through `dependent_work`, disclose earlier stopping points, and reject silent deadline propagation or uncertain replays. New child work follows its existing exact approval path.
- When verification or credentials expire before permission, the system shall return separate permission and readiness dates through `readiness`, retaining 0 seconds of grace for existing stale/token/checkpoint checks.
- The system shall return explicit selected-date consent, active Extend review, UTC/local dates, current usage and receipts through `owner_surfaces` at 1440 px and 390 px and supported native owner workflows, while rejecting wrong roles.
- The system shall return current effective expiry, remaining allowances and required owner action through existing CLI/MCP and manifest paths via `agent_surfaces`, rejecting delegated self-confirmations or caller-supplied owner substitutes.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: default_lifetime
 Given an existing approval within 24 hours
 When `default_lifetime` validates it without extended consent
 Then its prior behavior remains compatible
Scenario: extended_lifetime
 Given an expiry beyond 24 hours
 When `extended_lifetime` validates typed owner consent
 Then consent is required and the chosen finite date is retained
Scenario: extension_preview
 Given active exact authority with used resources
 When `extension_preview` selects a later date
 Then exact scope usage and dependent deadlines are reviewed together
Scenario: extension_confirm
 Given a current owner preview
 When `extension_confirm` rechecks time after acquiring the writer lock
 Then one idempotent immutable consent revision is committed
Scenario: extension_conflict
 Given expired revoked changed uncertain or concurrently amended authority
 When `extension_conflict` validates its preview
 Then no extension is committed
Scenario: accounting
 Given existing used calls and held commitments
 When `accounting` compares before and after extension
 Then IDs credentials limits usage and reservations remain unchanged
Scenario: automation_bundle
 Given a linked automation policy and source grant
 When `automation_bundle` extends permission
 Then both receipts commit or neither commits
Scenario: runtime_authority
 Given consented longer permission
 When `runtime_authority` checks the unchanged exact scope
 Then effective expiry is current and every other guard remains enforced
Scenario: dependent_work
 Given a child with an earlier original deadline
 When `dependent_work` checks only an extended parent
 Then the child cannot outlive its own consent or replay uncertain work
Scenario: readiness
 Given permission that outlives verification
 When `readiness` evaluates execution
 Then permission stays approved while stale execution remains paused
Scenario: owner_surfaces
 Given authenticated desktop and supported native owners
 When `owner_surfaces` reviews confirms extends and revokes
 Then explicit dates usage and receipts are inspectable and wrong roles reject
Scenario: agent_surfaces
 Given a delegated CLI or MCP agent
 When `agent_surfaces` inspects or proposes extension
 Then metadata is current and only an authenticated owner can confirm
```

## Architecture and scope
Source review: `.factory/authority-expiry-extension/architecture.md`, SHA256 `c45fb09086d18e6c6782e7ba707cfec605af87fda883a04ad89801fae081528c`. Use an append-only fixed-kind consent table and bounded parser/reader. Keep base records and history; legacy consent revision is zero. Amendments bind predecessor and unchanged base scope. Same request key/hash is idempotent; conflicting replay rejects. Changed base invalidates amendments.

New approvals can carry optional exact boolean `extended_expiry_consent`. For more than 24 hours it must be true in the reviewed owner body and persisted with approval. Consent is unavailable to agent self-approval. Active extension uses finite owner-only preview/confirm/history over existing authority kinds. The automation/grant bundle is atomic. Keep current CSRF/Origin or native fresh-owner checks.

Independent maker/checker packets, handoffs, discovery envelopes, OAuth/provider tokens, browser sessions and evidence freshness retain their own clocks. Parent extension does not rewrite old child packets. Existing work remains within original consent; newly prepared work follows current approval and cumulative parent accounting. Report any unsupported child renewal and its existing next action; do not add an automatic child-rebinding engine here.

Separate `permission_expires_at` from verification due/readiness. Fresh verification of unchanged scope preserves lifetime usage; changed bound facts require existing review. No operational WizeMe authority or account is extended by synthetic implementation tests.

## Authorized parameters
DEFAULT_HOURS = 24
timeout = 5
max_workers = 4

The UI decomposes one day into 24 hours (the DAY constant in its millisecond expression). This is the unchanged consent threshold, not a new maximum lifetime. Existing campaign form call defaults and free-only model spending remain the values declared below.

Synthetic fixtures deliberately use small cumulative allowances and finite test waits; these values are not new production limits:
max_calls = 2
max_calls = 3
max_calls = 4
max_calls = 10
max_calls = 20
max_calls = 40
max_calls = 500
max_model_minor = 0
DAY = 24
max_workers = 1
timeout = 10
