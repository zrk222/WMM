# WizeMe UTM observability audit

**Date:** 2026-11-08 (UTC)
**Scope:** Does a unique campaign tag survive from an approved organic post to
the landing and registration records WMM reports?
**Base commit:** `71351c2` (`main`, after PR #161)
**Method:** Source-bound review of the WMM repository plus targeted tests. No
live WizeMe site, production database or provider account was read for this
audit, so live persistence is **unproven**, not verified.

## Verdict

| Side | Status | Basis |
| --- | --- | --- |
| WMM accepts and preserves the exact tagged link | **VERIFIED** | `public_url(..., allow_tracking=True)`, round-trip test below |
| WMM generates one canonical link per study | **VERIFIED** | `tagged_url()` and `validate_tagged_url()` |
| WMM ingests and reports landing/registration with explicit coverage | **VERIFIED (local)** | contract and transport tests |
| WizeMe.APP records the UTM on the visit | **UNPROVEN** | requires live site evidence |
| The tag reaches the registration record | **UNPROVEN** | requires live source export |
| The source coverage is complete for both event types | **UNPROVEN** | requires live collector read |

Prior live record: E13 in
[`evidence/wizeme-dogfood-2026-11-03.json`](evidence/wizeme-dogfood-2026-11-03.json)
shows `campaign_tag_present: false` and
`decision: REVISE_TRACKING` for the earlier untagged post. E12 supplies an
aggregate baseline only.

## What WMM actually enforces

1. **Exact link.** `tagged_url()` builds a same-origin HTTPS URL with exactly
   `utm_source`, `utm_medium=organic`, `utm_campaign=<study_uuid>` and
   `utm_content=<creative_id>`. `validate_tagged_url()` rejects any other key,
   a different host, duplicate keys, blanks, a fragment or a re-encoded value.
2. **Exact destination retention.** Funnel definitions now call
   `public_url(..., allow_tracking=True)`, which preserves the raw query order
   and percent-encoding. A study link is accepted byte-identically.
3. **Event vocabulary.** Ingestion accepts only `LANDING` and `REGISTRATION`
   events with an opaque subject, `campaign_token` UUID or null, consent state,
   `bot` true/false/null and `internal_test`. Raw personal identifiers are
   rejected.
4. **Eligibility and exclusions.** A registration counts only when the same
   subject has an earlier eligible tagged landing by report `as_of`. Denied or
   unknown consent, bot true/null, internal tests, missing token, unmatched
   registrations and duplicates are reported as separate exclusion counts.
5. **Coverage.** Empty batches do not imply zero activity. Counts are null
   unless the source supplied complete coverage for that event type.
6. **Descriptive-only report.** The report is labelled
   `ATTRIBUTED_DESCRIPTIVE_ONLY` and omits install, revenue, lift, winner and
   causal fields.

## What WMM cannot verify from this repository

- Whether the WizeMe.APP landing page reads `utm_*` from the query string.
- Whether the app persists the tag on the registration record (first-touch or
  otherwise).
- Whether the private collector can export both event types for the exact
  window with complete coverage.
- Whether the provider actually served the post to humans.

These are runtime facts. WMM never scrapes the site DOM, never adds an SDK and
never exposes a public ingestion endpoint, so it cannot assert them from source.

## Findings

**A1 — Accepted link is not bound to a registered study.** A funnel can store
any allowlisted UTM link, including one that does not match a study's canonical
URL. This is by design (funnels are plans), but it means an operator could
publish a *different* tag than the one the study will validate. Mitigation:
paste the generated link unchanged; the owner checklist does this. A future
binding check would be a separate reviewed change.

**A2 — The funnel layer is not the verification layer.** Passing
`allow_tracking=True` proves the link is well-formed and retained. It does not
prove the tag reached the records. Treat the study report — not the funnel
definition — as the evidence.

**A3 — No install or revenue linkage.** Consistent with the study spec. A
`TRACKING_VERIFIED_CONTINUE` decision must not be reported as installs,
activation, revenue or lift.

**A4 — Coverage is the likely failure mode.** The earlier trial failed on a
missing tag, not on ingestion. The next trial can still return null counts if
the collector cannot prove complete coverage; the decision rule treats that as
`COVERAGE_INCOMPLETE_COLLECT`, not zero.

## Regression evidence

`tests/test_funnel_contract.py` now asserts that a generated study link passes
through the funnel definition unchanged:

```python
link = tagged_url('https://wizeme.app', dict(
    id='11111111-1111-1111-1111-111111111111', source='facebook',
    creative_id='creative_01', landing_path='/welcome'))
assert definition(dict(self.plan, destination=link))['destination'] == link
```

Existing coverage that this audit relies on:

- `tests/test_observational_campaign_contract.py` — URL construction,
  exact-match validation and rejection cases.
- `tests/test_observational_campaign_transport.py` — ingestion, collisions,
  corrections, coverage and report semantics.
- `tests/test_observational_campaign.py` — end-to-end local study lifecycle.
- `tests/test_funnel_contract.py` — UTM acceptance and rejection matrix.

## Live verification procedure (owner-run)

1. Register the study and copy the generated URL unchanged.
2. Publish the one approved post; save the provider ID and permalink.
3. Open the landing page from the post on a clean device; confirm the exact
   `utm_*` values in the request URL and in whatever the app records (browser
   devtools, first-party analytics event, or database row).
4. Complete a registration on the same subject.
5. After `ends_at`, export both event types with explicit coverage and ingest
   them.
6. Read the report. `TRACKING_VERIFIED_CONTINUE` requires eligible landings,
   linked registrations, complete coverage and the pre-set minima.

Until steps 3–6 produce receipts, the correct statement is: **WMM is ready; the
site and source are unproven.**

## Non-claims

No claim of traffic, registrations, installs, revenue, retention, causal lift,
time savings or successful attribution is made by this audit.
