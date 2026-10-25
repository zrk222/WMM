# Spec: growth-funnels
Status: requirements

## MUST - Functional core
### Description
Connect WMM creative production to consented customer acquisition and measured subscription outcomes. Keep app acquisition simple; avatars and resource handoffs are optional; the conversion destination is app sales.

### Requirements (EARS)
- The system shall store an immutable app-owned funnel definition binding manifest version, creative source hashes, audience, measurable outcome, pain-point evidence, hook, CTA, destination, cohort and attribution window through `funnel_scope`.
- The system shall return a stage graph for the selected app-download, resource or app-demo route with explicit free and paid deliverables and app plan or feature tiers through `funnel_stages`.
- The system shall reject duplicate conflicting observations and store idempotent source-bound stage observations with observed, partial or unknown coverage and opaque identities through `funnel_observations`.
- The system shall return stage counts, eligible denominators, drop-off and conversion timing only for comparable cohort and window scope while returning null for missing or invalid denominators through `funnel_rates`.
- The system shall return currency-separated acquisition and production cost per install, activation, trial and payer using existing subscription ledger references for at most 500 observations per import without duplicating payments or subtracting refunds twice through `funnel_economics`.
- The system shall reject stale app versions, source hashes, revoked grants and unsupported provider actions across shared UI, CLI and MCP operations through `funnel_controls`.
- The system shall return reviewable provider-supported keyword, resource and messaging handoff plans with eligibility, consent, expiry, delivery and uncertain-result recovery states without granting message or spend authority through `funnel_handoff`.
- The system shall emit founder-review bottlenecks, workflow stage telemetry and PDF plus structured reports with provenance and unknowns while excluding private contact details through `funnel_review`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: funnel_scope
  Given a selected app and declared evidence scope
  When `funnel_scope` processes current or invalid inputs
  Then the declared scoped outcome is returned and invalid or unavailable evidence remains explicit
Scenario: funnel_stages
  Given a selected app and declared evidence scope
  When `funnel_stages` processes current or invalid inputs
  Then the declared scoped outcome is returned and invalid or unavailable evidence remains explicit
Scenario: funnel_observations
  Given a selected app and declared evidence scope
  When `funnel_observations` processes current or invalid inputs
  Then the declared scoped outcome is returned and invalid or unavailable evidence remains explicit
Scenario: funnel_rates
  Given a selected app and declared evidence scope
  When `funnel_rates` processes current or invalid inputs
  Then the declared scoped outcome is returned and invalid or unavailable evidence remains explicit
Scenario: funnel_economics
  Given a selected app and declared evidence scope
  When `funnel_economics` processes current or invalid inputs
  Then the declared scoped outcome is returned and invalid or unavailable evidence remains explicit
Scenario: funnel_controls
  Given a selected app and declared evidence scope
  When `funnel_controls` processes current or invalid inputs
  Then the declared scoped outcome is returned and invalid or unavailable evidence remains explicit
Scenario: funnel_handoff
  Given a selected app and declared evidence scope
  When `funnel_handoff` processes current or invalid inputs
  Then the declared scoped outcome is returned and invalid or unavailable evidence remains explicit
Scenario: funnel_review
  Given a selected app and declared evidence scope
  When `funnel_review` processes current or invalid inputs
  Then the declared scoped outcome is returned and invalid or unavailable evidence remains explicit
```

## WON'T - Out of scope
This specification does not authorize publication, messages, ad spending, provider activation, live paywall changes or financial transactions. No universal avatar advantage, retention cutoff, six-month mandate, price point, conversion benchmark or guaranteed income. Provider eligibility and subscription access must be verified, not inferred. Existing ledger events remain authoritative for subscription outcomes. Preparation is distinct from real execution and measured lift.

## Implementation acceptance detail
App-owned immutable definitions and revisions survive restart. Snapshot import/export excludes credentials and grants. Route changes require a new reviewed version. Keep research citations and content hashes, distinguish source removal and expiry, and preserve old observations.

A source observation declares source identity/hash, observation window, cohort, metric/unit, denominator definition, coverage and evidence provenance. Observed zero differs from missing. Anonymous aggregate stage ratios must not become person-level conversion or causal attribution. Cohort subject joins require an explicitly supplied matching identity contract. Never infer people from views.

Display three-second retention only if actually observed; show sample and denominator. Compare hook/script/persona/CTA variants under declared test scope. Optional avatar use requires actual audio/video review and user-selected provider access; no silent paid fallback.

Provider handoff needs exact account/action/trigger/limits/expiry scope, current credentials, consent and provider eligibility. Follower DM is not universally available. Comment private reply is distinct from an opened messaging window. Unknown sends are reconciled without automatic replay. Retargeting choices reflect actual provider capabilities; campaign recommendations cannot initiate spend.

Outcome briefs state audience, measurable milestone, source-backed pain, hook, CTA and free/paid boundary. The sales workflow demonstrates the actual app, matches its app/store destination, follows install and onboarding, verifies first value and reviews localized trial, checkout and restore. App tiers reflect actual features, billing periods, trial eligibility and entitlements. No webinar, event or coaching workflow is included. Live pricing and paywall changes remain separately authorized.

Required profiles: deterministic unit and actual local persistence/restart; app and role isolation; exact HTTP plus CLI and official MCP conformance; desktop/mobile real browser, keyboard/focus and reports; native creative linkage; separately authorized real provider handoff. All applicable CF and workflow QA gates plus clean hosted CI are required. These profiles are not yet executed for this feature.

## Architecture decision: reuse domain evidence, persist funnel identity

The existing customer_workflow_store provides immutable pain-point research and source expiry. creative_briefs contains hooks, CTA, destination and first_value. acquisition_workflows contains source-bound acquisition hypotheses. ledger and subscription_journey already retain app/cohort-separated installs, activation, purchases, renewals, cancellations and refunds. Do not create shadow copies of those events as funnel revenue.

Persist only two new app-scoped resources: immutable funnel definitions and immutable upstream stage observations. Existing domain rows are referenced by kind, identity, version and SHA256. Reports resolve exact current references; removal, hash change or app-manifest mismatch returns SOURCE_REVIEW_NEEDED. Historical reports retain their frozen source set; current views do not rewrite prior evidence. This is a proposed architecture, not an assertion that these resources exist.

Definition envelope: id, manifest_version, data. Data: release, locale, currency, cohort_id, outcome (audience, pain, research_refs, milestone, metric, target, due_at), creative_refs, hook, cta, destination, route, stages, attribution (method, identity_scope, starts_at, ends_at, conversion_window_seconds), offer_boundary (free_deliverables, paid_deliverables), optional content cadence and app plan tiers. Route is APP_DOWNLOAD, RESOURCE or APP_DEMO. Stage identifiers and edges are explicit, unique and acyclic; optional branches do not silently contribute to denominators. Start with at most 32 stages, 20 creative references and 10 app plan tiers per definition. Targets are user hypotheses, never observed outcomes.

Observation envelope: id, manifest_version, definition_id, definition_hash, data. Data: stage_id, metric, unit, source_ref, source_sha256, cohort_id, starts_at, ends_at, observed_at, coverage, count, denominator_definition, identity_scope, optional opaque subjects. At most 500 observations per import. OBSERVED count may be zero; PARTIAL counts remain partial; UNKNOWN requires null count. No emails, phone numbers, account secrets or raw private transcripts. Opaque subjects are accepted only with an explicit source identity contract; aggregate-only rows cannot establish subject-level conversion or transit time. Event identity is app/source/event scoped, exact duplicate idempotent, conflicting duplicate rejected atomically.

A report joins existing ledger outcomes only for an exact cohort, currency and observation window. A stage rate requires declared matching eligibility/population definitions and numerator no greater than denominator; otherwise return null plus the concrete mismatch. Views are not unique people and multi-touch campaign estimates are labeled separately from observed subject joins. Costs state source, currency and included categories; unavailable production or acquisition cost prevents a complete combined-cost claim. Do not convert currencies or value leads automatically. Do not rank a bottleneck from incomparable, partial or absent stage data.

Use owner-authorized local evidence writes and the existing reviewed-dispatch/grant service; HTTP, CLI and MCP call one service. Agents cannot approve themselves. Funnel read, definition save, observation import, report and handoff prepare are separate operations. Actual external send is a separately implemented effect adapter with exact current approved scope and receipt reconciliation. Unsupported effects remain explicit missing capabilities rather than executable plans.

UI sequence: outcome and audience; evidence and creative; destination and optional capture; review/run; results and next action. Keep detailed denominators, source provenance and optional acquisition branches in expandable views. Every stage states input, action, expected artifact and observed result. PDF and structured report share one redacted report model. An empty funnel suggests the first required action and never pretends to run a provider.

Validation order: exact schema and pure graph/observation reducers; transactional persistence/idempotency and ledger linkage; authority plus transport conformance; real human desktop/mobile workflows and reports; optional provider acceptance. A local fixture does not establish provider eligibility or real revenue. Broad goal remains active until all required acceptance profiles pass.

## Current backend packet and remaining implementation

The first packet implements typed app-sales definitions, native creative/customer evidence binding, immutable SQLite storage, deduplicated upstream aggregate observations, source-status readback and cautious aggregate reporting with the existing cohort ledger. It does not expose a UI/HTTP/CLI/MCP funnel workflow yet. No complete funnel, conversion-timing, production-cost coverage, provider handoff or full goal claim is made.

Current supported source kinds are CREATIVE_BRIEF and CUSTOMER_WORKFLOW. Customer workflow references use version1 because their IDs are immutable; creative briefs bind their latest exact native version. Exact release/locale/currency and acquisition window must match the existing app-owned cohort. Retain at most 1000 immutable definitions per app and 10000 observations per definition; import at most 500 observations atomically. Capacity errors preserve history instead of deleting data. These bounds do not establish performance measurements.

Reports select the latest full-window snapshot for one source rather than add overlapping aggregates. Equal-time contradictory snapshots and multiple distinct source identities remain unresolved. An edge ratio requires observed counts, matching units and declared eligible population, a positive denominator and numerator no greater than denominator. It is labeled a supplied aggregate ratio, never verified individual conversion. Refund-adjusted financial values are passed through from the authoritative ledger without arithmetic duplication. First-value/payment timing and comprehensive production-cost coverage remain explicitly unestablished until their intended source linkage is implemented.

Remaining: render-artifact creative links, app-plan/upgrade metadata, time-to-convert from verified identity joins, production cost integration, optional cadence controls, snapshot portability, guarded shared transport, full user interface, founder review, reports/export, provider handoff and all original acceptance profiles. Parent FUN01–08 scope remains unchanged.
