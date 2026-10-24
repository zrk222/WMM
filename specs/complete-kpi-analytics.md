# Spec: complete-kpi-analytics
Status: approved scope; implementation pending

## MUST - Functional core
### Description
UPG-08 adds a versioned KPI catalog, durable collection and analytics coverage across every supported WMM workflow, including agent-made video. Record underlying observations and reproducible derived values. An uncollected KPI is a visible coverage gap, not an observed zero. This is additional required goal scope authorized October 24, 2026.

### Requirements (EARS)
- The system shall store an inventory of every supported feature and connector against acquisition, activation, revenue, retention, campaign, creative, agent-operation and data-quality KPI families through `coverage_catalog`.
- The system shall store the source, collection method, unit, grain, formula, dimensions, observation window, timezone, maturity rules, permissions and retention policy for each KPI through `metric_definitions`.
- The system shall durably store source-identified app-owned observations with occurrence and ingestion times, event identity, definition version and correction lineage through `durable_observations`.
- The system shall reject duplicate source events, retain permitted late corrections and resume checkpointed backfills without double counting through `ingestion_recovery`.
- The system shall compute aggregates using declared denominators, mature cohorts, compatible currencies and provider definitions while distinguishing observed zero, partial, stale, estimated and unavailable values through `reproducible_analytics`.
- The system shall display source freshness, coverage gaps and required connector permissions on the relevant explained UI pages with matching scoped PDF and machine-readable exports through `page_reporting`.
- The system shall reject cross-app and missing-consent observations and redact reports under the declared source retention policy without inferring cross-device identity through `privacy_boundaries`.
- The system shall store local collection tests and authenticated source readback as distinct evidence classes with per-collector acceptance status through `collector_acceptance`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: coverage_catalog
  Given the supported feature and connector inventory
  When KPI coverage is inspected through `coverage_catalog`
  Then every feature has explicit metric mappings and each absent collector is named
Scenario: metric_definitions
  Given a derived metric without a source or denominator definition
  When its definition is registered through `metric_definitions`
  Then it is rejected before dashboard publication
Scenario: durable_observations
  Given an app-owned normalized source observation
  When storage is reopened through `durable_observations`
  Then its source identity, times, definition and correction lineage remain available
Scenario: ingestion_recovery
  Given duplicate events and an interrupted historical backfill
  When ingestion resumes with late corrections through `ingestion_recovery`
  Then duplicates are excluded and reconciled aggregates retain their source lineage
Scenario: reproducible_analytics
  Given mixed currencies, immature cohorts and missing observations
  When aggregates are requested through `reproducible_analytics`
  Then incompatible values are separated and missing values are not zero
Scenario: page_reporting
  Given a scoped dashboard and its metric explanation
  When PDF and machine-readable reports are exported through `page_reporting`
  Then source freshness, filters, totals and collection gaps match the dashboard
Scenario: privacy_boundaries
  Given another app's observation or missing required consent
  When ingestion or reporting is attempted through `privacy_boundaries`
  Then unauthorized data is excluded and credentials and customer identifiers are not exported
Scenario: collector_acceptance
  Given local test fixtures without authenticated source readback
  When readiness is reported through `collector_acceptance`
  Then external collection remains unverified and the named acceptance dependency is retained
```

## SHOULD - Required coverage
- Acquisition: reach, impressions, listing/search visibility, views, clicks, installs, source attribution, ad spend and defined CTR/CPC/CPM/CPI/CAC.
- Activation: onboarding, first value, time to value, funnel drop-off, paywall exposure, trial starts and mature trial-to-paid conversion.
- Revenue: first payment, renewal, cancellation, expiration, billing failure/recovery, refunds, net proceeds, contribution and defined recurring-revenue measures.
- Retention: active users, repeat use, cohort retention, customer/revenue churn and observed feature engagement.
- Experiments: exposure, assignments, samples, maturity, supported uncertainty, guardrails, decisions, rollback and downstream outcomes.
- Creative: asset and variant lineage, render count/success/failure/duration/retry/reuse/cost and available published views, watch time, retention, completion, shares, saves, comments, clicks and conversions.
- Agents: observed requests, tokens, tool use, latency, approvals, failures, cancellations, quotas, rate limits and estimated versus billed costs.
- Data quality: freshness, lag, completeness, invalid/duplicate/corrected events, permission errors, missing attribution and export outcomes.

## SHOULD - Technical
- Start with an authoritative inventory; extend existing event, ledger, cohort, report and connector infrastructure before adding parallel storage.
- A generic event store alone does not implement the collectors or analytics. Every declared metric must map to source, collector, storage, computation, UI and export acceptance.
- Separate cash, entitlement, revenue run rate and estimates. Do not sum incompatible unique-user populations or provider engagement definitions.
- Verify authorized real source observations for connected collectors. Name missing access or provider capabilities individually and complete independent local work.
- Require CF architecture, source-bound workflow QA, meaningful negative cases, migration/recovery, regression, privacy and real desktop/mobile/PDF acceptance before a complete-analytics claim.
