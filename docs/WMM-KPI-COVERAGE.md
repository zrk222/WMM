# Complete analytics: report-to-acceptance coverage

The 2026-10-25 report is incorporated into existing UPG-08. All eight KPI families remain required. This matrix records definitions and missing stages; it does not implement collectors.

## Report corrections

- Apple Ads read and derived CPI/CPT/CR/TTR already exist.
- Supplied cohort CAC and useful-value retention and subscription conversion already exist.
- RevenueCat overview is not exact individual LTV or an MMP identity join.
- No assumption that existing Android Publisher permission grants GCS analytics download.

## Required metrics

| Metric | Current coverage | Definition |
|---|---|---|
| CPI | PARTIAL_APPLE_ADS | spend / attributed installs |
| CPA | MISSING | matched cost / deduplicated named actions |
| CAC | PARTIAL_SUPPLIED_COHORT | matched acquisition cost / distinct acquired payers |
| ROAS_D7 | MISSING | attributed cohort revenue through day7 / matched cohort spend |
| ROAS_D30 | MISSING | attributed cohort revenue through day30 / matched cohort spend |
| PAYBACK | MISSING | first mature horizon cumulative net contribution recovers acquisition cost |
| LTV_CAC | MISSING | same-cohort declared observed or modeled LTV / same-cohort CAC |
| STORE_CVR | MISSING_STORE_ANALYTICS | provider-defined first acquisition / eligible listing visitors |
| STORE_IMPRESSIONS | MISSING_STORE_ANALYTICS | provider count at declared unique or total grain |
| KEYWORD_RANK | MISSING_ORGANIC_RANK | dated store-country-locale-device query position |
| LISTING_EXPERIMENT | MISSING | provider-exposed variant views installs and declared uncertainty |
| AD_FUNNEL | PARTIAL_APPLE_ADS | impressions taps installs spend with source-defined CTR CPT CPI CPM |
| TRIAL_PAID_BY_SOURCE | MISSING_SOURCE_JOIN | mature eligible trial starters converted to first successful paid / trial starters by attributed source |
| TIME_TO_VALUE | PARTIAL_REQUIRES_EVENT_SEMANTICS | elapsed first qualifying useful-value event minus install or first session |
| PAYWALL_TRIAL_FUNNEL | PARTIAL_SUBSCRIPTION_LEDGER | unique eligible users at onboarding paywall trial and paid steps |
| NRR | MISSING | opening recurring revenue + same-cohort expansion - contraction - churn over opening recurring revenue |
| ARPPU | MISSING | declared period revenue / distinct eligible paying users in period |
| ARPU | MISSING | declared period revenue / distinct eligible users in period |
| MRR_ARR | PARTIAL_PROVIDER_OVERVIEW | provider-defined normalized recurring run-rate; not realized cash |
| REFUNDS_NET_CONTRIBUTION | PARTIAL_REFUND_FIX_IN_PROGRESS | net proceeds after refunds - delivery costs - acquisition costs |
| RENEWAL_CHURN | PARTIAL_SUBSCRIPTION_LEDGER | mature subscription renewal cancellation expiration billing failure and recovery by contract |
| RETENTION_D1 | MISSING_DAY_N | qualifying day1 retained first-install users / mature observable first-install cohort |
| RETENTION_D7 | MISSING_DAY_N | qualifying day7 retained first-install users / mature observable first-install cohort |
| RETENTION_D30 | MISSING_DAY_N | qualifying day30 retained first-install users / mature observable first-install cohort |
| VALUE_RETENTION | PARTIAL_SUPPLIED_COHORT | retained useful-value subjects / mature eligible subjects at declared app cadence |
| UNINSTALL | MISSING_COLLECTOR | provider-defined device or user deletions with compatible cohort/base denominator |
| PUSH_OPTOUT | MISSING_COLLECTOR | unique newly opted-out consented recipients / eligible opted-in recipients in window |
| ACTIVE_USERS | MISSING_UNIQUE_AGGREGATION | deduplicated active users or devices for explicit day week month windows |
| K_FACTOR | MISSING | deduplicated invites per eligible inviter times eligible referred conversion |
| REFERRAL_CONVERSION | MISSING | deduplicated successful referred new users / eligible referral recipients or clicks with explicit denominator |
| EXPERIMENT_EXPOSURE | PARTIAL | assignment exposure sample ratio maturity contamination and guardrail coverage |
| EXPERIMENT_OUTCOME | PARTIAL | predeclared conversion lift uncertainty rollback and downstream outcome status |
| VIDEO_ATTENTION | MISSING_PUBLISHED_COLLECTORS | platform-specific views reach hook hold watch time and completion with denominator |
| VIDEO_ENGAGEMENT | MISSING_PUBLISHED_COLLECTORS | likes comments shares saves and clicks using compatible provider grain |
| CREATIVE_CONVERSIONS | MISSING_SOURCE_JOIN | source-creative matched activation trial paid and revenue |
| RENDER_OPERATIONS | PARTIAL_JOB_RECORDS | render success failure duration retry reuse artifact lineage and measured machine/model costs |
| AGENT_USAGE | PARTIAL_PER_JOB | reported input output cached and total tokens by job/model/provider without inferred billing |
| AGENT_COST | MISSING_AGGREGATE_BILLING | actual billed cost separate from estimate and unknown; account quota/rate-limit observations |
| AUTONOMY_OPERATIONS | PARTIAL_TELEMETRY | tool calls stage latency approval wait failures cancellation recovery and scope stops |
| SOURCE_FRESHNESS | PARTIAL | last observed/ingested successful read age lag and expected update cadence |
| INGESTION_QUALITY | PARTIAL_DOMAIN_STORES | invalid duplicate corrected late unmatched and backfilled observation coverage |
| EXPORT_QUALITY | PARTIAL | report filters totals source coverage download/print outcome and retained audit lineage |

## Required proof for each metric

- Numerator denominator and grain are explicit and compatible.
- Unknown or missing evidence is null/unavailable; no fabricated zero or source join.
- Durable raw observations and dedup/correction lineage reproduce the calculation.
- Collector access and authenticated readback are separate from fixture proof.
- Human UI agent API analytics and PDF/CSV/JSON exports agree on filters units freshness and coverage.

Day-N retention requires an explicit exact-day versus rolling-day convention, mature eligible population and qualifying useful event. Do not compare unlike retention definitions.
Uninstall/deletion counts and generic daily installs do not automatically form a same-cohort churn rate. Opt-in coverage and user/device identity limits remain visible.
NRR excludes revenue from newly acquired customers. Observed fixed-horizon revenue and modeled lifetime value remain distinct. Do not double-subtract refunds from net proceeds.
Provider-native CVR definitions are retained: listing-view conversion is not Apple Ads taps-to-install conversion. Keyword rank is a dated observation, not implied by keyword ad reports.

## Shared workflow and export coverage

Local/Drive media imports, viral qualification, agent and human edits, Hypit renders and autonomous runs must also record source lineage, rights, stage timing, actual observed cost and completion/recovery. No render or share count is promoted into a viral or causal revenue claim.
Canonical machine-readable matrix: specs/kpi-report-coverage.json. Full acceptance contract: specs/complete-kpi-analytics.md.

## Verified provider boundaries

- [developer.apple.com](https://developer.apple.com/help/app-store-connect-analytics/engagement/app-usage): Usage/deletion data covers opted-in diagnostic/usage sharing, not all users.
- [support.google.com](https://support.google.com/googleplay/android-developer/answer/6135870?hl=en): Statistics and acquisition CSV exports use private GCS; devstorage.read_only and Play account permissions must be verified separately.
- [developers.google.com](https://developers.google.com/workspace/drive/api/guides/api-specific-auth): drive.file plus Google Picker grants selected-file access; OAuth metadata access alone is not a content download grant.
