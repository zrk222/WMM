# Spec: growth-review-history
Status: draft

## MUST - Functional core
### Description
Connect existing upgrade validators and actual saved account reads to immutable founder-review history. Editorial notes and imported snapshots grant no authority. This packet retains the full requested feature set; integration is not product completion.

### Requirements (EARS)
- The system shall store immutable app-owned listing, benchmark-reference and editorial-note entries with original data, source hashes and creation time through `immutable_history`.
- The system shall reject changed manifest versions, mismatched release, locale or currency and cross-app target identities through `scope_guard`.
- The system shall return current preflight and benchmark freshness while retaining up to 1000 rows of expired or changed evidence through `fresh_readout`.
- The system shall return benchmark observations derived from app-owned successful Apple Ads jobs with exact report and connection binding through `ads_projection`.
- The system shall reject incompatible periods, metrics, currencies, placement or source coverage before returning an advisory difference through `benchmark_comparison`.
- The system shall store portable history atomically and reject malformed, duplicate or tampered entries without importing execution authority through `portable_history`.
- The system shall return unified founder review through the loopback service with distinct local, provider and outcome evidence states and zero external writes through `review_api`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: immutable_history
  Given app-owned source history
  When `immutable_history` is exercised
  Then its valid behavior is observed and invalid or stale scope cannot gain authority
Scenario: scope_guard
  Given app-owned source history
  When `scope_guard` is exercised
  Then its valid behavior is observed and invalid or stale scope cannot gain authority
Scenario: fresh_readout
  Given app-owned source history
  When `fresh_readout` is exercised
  Then its valid behavior is observed and invalid or stale scope cannot gain authority
Scenario: ads_projection
  Given app-owned source history
  When `ads_projection` is exercised
  Then its valid behavior is observed and invalid or stale scope cannot gain authority
Scenario: benchmark_comparison
  Given app-owned source history
  When `benchmark_comparison` is exercised
  Then its valid behavior is observed and invalid or stale scope cannot gain authority
Scenario: portable_history
  Given app-owned source history
  When `portable_history` is exercised
  Then its valid behavior is observed and invalid or stale scope cannot gain authority
Scenario: review_api
  Given app-owned source history
  When `review_api` is exercised
  Then its valid behavior is observed and invalid or stale scope cannot gain authority
```

## SHOULD - Technical
- Bound retained history to 1000 entries per app. Use exact immutable identity replay and optimistic current manifest checks.
- Listing data must match current release and locale. Reference currency must match the explicitly configured app currency.
- Editorial notes may choose KEEP, REVISE or DEFER and must reference an exact same-app source hash. They are local notes, not authenticated human approval.
- Apple Ads metrics come from saved successful campaign or keyword reads, never caller-supplied aggregate totals. Classification fields category, territory, placement and campaign type remain explicitly operator-declared; provider verification is not inferred.
- Retain provider-returned currency and explicit UTC inclusive report-date mapping. Search-term account-local timezone reports require separate timezone support before comparison.
- Monetary conversion uses explicit minor-unit profiles; unsupported units or missing metrics return unavailable rather than assume a conversion. No FX conversion.
- Revoked or rotated connections, changed reports, expired datasets and imported source assertions cannot silently become current provider evidence.
- No network requests, provider mutation, live purchases, advertising spend, publication or production activation occur in these local projections.
- Full UI and generic-agent coverage remain required follow-up work and cannot be omitted to close the objective.

## Authorized parameters
The following bounds apply to app-owned immutable entries and text.
MAX_ENTRIES = 1000
MAX_TEXT = 2000
CURRENCY_DIGITS = 0
CURRENCY_DIGITS = 2
CURRENCY_DIGITS = 3
CURRENCY_DIGITS = 4
prec = 96

ISO minor-unit profiles are frozen from the official SIX ISO 4217 current-currency list, published 2026-09-17. The source URL and exact source SHA256 are retained beside the generated fact table. Do not substitute currency display rounding or cash rounding for ISO minor units.
