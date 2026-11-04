# Spec: market-research-depth
Status: approved

## MUST — Functional core
### Description
Save bounded, immutable, app-scoped market research snapshots for a founder reviewing localized search phrases and competing listings. Every result is descriptive and advisory.

### User roles
- Local founder reviewing app-owned evidence and analyst hypotheses.

### Requirements (EARS)
- The system shall accept a snapshot for exactly one configured app release and locale, with explicit platform (`iOS` or `Android`) and territory.
- The system shall accept at most 20 dated source snapshots, 50 keyword phrase records, and 10 competitor listing records per entry; source excerpts are at most 1000 characters, phrase text at most 120 characters, and competitor listing excerpts at most 1000 characters.
- The system shall reject any source that lacks a unique ID, safe HTTPS URL, SHA-256 of the captured evidence, retrieval timestamp less than or equal to observation time, and explicit coverage state `COMPLETE`, `PARTIAL`, or `NO_RESULTS`.
- The system shall store at most 50 phrase records per entry, each `observed` and `inferred` objects as separate fields, and mark inferred analysis `ANALYST_INFERRED`.
- The system shall reject duplicate IDs or normalized phrases, malformed or future timestamps, nonfinite or negative supplied metrics, unbound sources, mixed app release or locale, extra fields, secrets, and unsafe URLs.
- The system shall return the named `search_volume`, `rank`, and `difficulty` metrics as null when no source ID is supplied; when supplied, each metric shall include `provenance=OPERATOR_ASSERTION` and `provider_verified=false`, and paid ad counts shall not populate these metrics.
- The system shall return deterministic normalized phrase coverage, keyword and competitor phrase overlap, and test candidates under declared rules, with explicit no-result, partial and stale states and next actions; invalid source-less snapshots shall be rejected.
- The system shall bind saved evidence to app context and immutable content hashes, returning an independent stale-scope status when the app manifest changes even for imported assertions, and rejecting changed replay under the same identity.
- The system shall make no network calls or external writes and shall not infer growth, paid performance, organic rank, or causal outcomes.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Scoped evidence and inference
  Given one current app release and locale with dated source snapshots
  When a market research entry is saved and read
  Then source-backed observations and analyst inferences remain separately labeled and hash-bound

Scenario: No result and partial evidence
  Given a source reports no results or partial coverage
  When candidates are evaluated
  Then missing values remain null and the report gives a concrete next action

Scenario: Paid counts cannot become organic claims
  Given a saved Apple Ads keyword report or supplied paid counts
  When a market research snapshot is evaluated
  Then volume, difficulty, and organic rank remain unavailable unless explicitly sourced as operator assertions

Scenario: Invalid or changed evidence
  Given unsafe URLs, duplicate phrases, malformed dates, or changed content under an existing ID
  When input is validated or replayed
  Then the entry is rejected without network access or mutation of retained history

Scenario: App context changes
  Given saved research and a changed app manifest
  When history is read
  Then the record is marked stale and its evidence remains preserved
```

## SHOULD — Technical/structural
- Data model: immutable `MARKET_RESEARCH` GrowthReviews entry with exact app context; source snapshots, keyword records with `observed`, `inferred.intent`, `inferred.relevance`, and metric source IDs, competitor listing records, explicit metrics, derived `phrase_overlap`, coverage, and candidate rules.
- API contract: existing `growth.save` / `growth.read`; no new operation or database table.
- Limits: sources 20, phrases 50, competitors 10, phrase text 120 chars, excerpt 1000 chars, snapshot total JSON 64 KiB, analysis candidates 25.

## Authorized parameters
MAX_SOURCES = 20
MAX_PHRASES = 50
MAX_COMPETITORS = 10
MAX_EXCERPT = 1000
MAX_PHRASE = 120
MAX_BYTES = 65536

## SHOULD NOT — Implementation details
- Do not fetch source URLs, scrape providers, change app listings, authorize spending, or treat operator assertions as verified provider measurements.

## Decision logic (factory candidates)
| # | if | then |
|---|----|------|
| 1 | No phrases exist or all sources have coverage `NO_RESULTS` | Return `NO_RESULTS` and next action `Capture a broader query` |
| 2 | Source coverage has aged beyond 90 days and phrases exist | Return `STALE` and require a current capture |
| 3 | Phrases exist and current sources include `PARTIAL`, or mix `NO_RESULTS` with another coverage state | Return `PARTIAL` and require a complete source capture |
| 4 | Source coverage is `COMPLETE` and phrases exist | Return `OBSERVED` for supplied evidence, without provider verification |
| 5 | `phrase_overlap=true` from supplied own and competitor listing excerpts | Mark overlap from supplied text and propose a differentiating copy test |
| 6 | `inferred.intent` or `inferred.relevance` exists and metric source IDs are absent | Keep test candidate with metric fields null |
