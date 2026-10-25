# Useful marketer workflows added to the WMM goal

Reviewed 2026-10-25 against the supplied missing-gaps report and current source.
Latest user instruction: integrate only useful workflows and UX into the active goal.
All original UPG-00 through UPG-06 and prior additive requirements remain.

## Corrected baseline

- ASC and selected build/localized keyword/release-note reads already exist.
- Apple attribution, Apple Ads reports, local follow-up and verified webhook intake already exist.
- Unverified revenue-share percentages and blanket product suitability verdicts are not adopted.

## Required workflows

### MW-01 - Unified iOS release and listing readiness (P1)

PARTIAL: ASC selected version/build, localized keywords/release notes, subscriptions and reviews exist.

Workflow: Join existing iOS facts to pipeline blockers with source time, missing access and a concrete repair. Add TestFlight/crash reads where they support a release decision.

Acceptance:

- No duplicate Apple connector; selected app/build/locale and partial pagination remain explicit.
- Stale, foreign-app and permission failures reject; unavailable TestFlight/crash data stays unknown.

Status: REQUIRED_NOT_COMPLETE.

### MW-02 - Attribution to campaign CPA and mature ROAS (P0)

PARTIAL: Apple native attribution and ad reports exist; MMP cohort/cost joins are missing.

Workflow: Import permitted MMP and cost exports; map exact app/campaign/creative cohorts to costs and revenue for spend-review decisions. Add native connections when recurring use justifies them.

Acceptance:

- D7/D30 include cohort dates, maturity, currency, timezone, attribution model/window, revenue basis and refunds.
- Missing cost/revenue or zero denominators yield unavailable metrics; incompatible sources and overlapping revenue cannot be summed.
- Deduplication, unmatched coverage, foreign apps, bad units and saved provenance are tested.

Status: REQUIRED_NOT_COMPLETE.

### MW-03 - Campaign brief to validated upload bundle (P0)

MISSING broader network export; Apple Ads observations and bounded provider actions exist.

Workflow: Build campaign/ad-group-or-ad-set/ad drafts from objective, audience, budget, bid and rights-cleared creative; review diff and export platform-specific CSV/JSON. Start with Apple Ads and the user-selected network.

Acceptance:

- Validate hierarchy, required fields, budget/currency units, destinations, assets, locale and keyword match types.
- Preview exact outbound fields, schema version and errors; prove round-trip against a provider-format fixture.
- DRAFT_EXPORTED is separate from provider accepted/active; no export activates spending.

Status: REQUIRED_NOT_COMPLETE.

### MW-04 - Review inbox to approved response draft (P1)

PARTIAL: ASC review reads exist; unified Apple/Play triage and response drafts are missing.

Workflow: Filter reviews by issue, rating, recency and response status; link product evidence and draft an editable reply. Preserve original text and separate sentiment inference from confirmed incidents.

Acceptance:

- Show coverage, deduplication, translation/source distinction and draft history.
- Draft, approved and published remain distinct; posting needs exact approval and readback.
- Human and agent can inspect/edit; private identifiers stay out of model context and exports.

Status: REQUIRED_NOT_COMPLETE.

### MW-05 - Retention problem to consented lifecycle experiment (P1)

PARTIAL: local follow-up policy, eligibility and handoff exist; CRM lifecycle tracking is missing.

Workflow: Draft push/in-app/email variants; select consented segment, quiet hours, cap, schedule and holdout; approve export/handoff and import delivery/conversion/unsubscribe outcomes. Add the connected CRM adapter required by this workflow.

Acceptance:

- Extend existing follow-up instead of a second scheduler; suppression and withdrawn consent prevent dispatch.
- Scheduled, handed off, delivered and converted remain distinct; missing delivery is unknown.
- Replay, timezone, cancellation, revocation and stale-segment approvals are tested.

Status: REQUIRED_NOT_COMPLETE.

### MW-06 - Competitor evidence to a testable hypothesis (P2)

PARTIAL: benchmarks and creative library exist; competitor export/feed ingestion is missing.

Workflow: Attach permitted listing, keyword and ad-library evidence to existing libraries; compare exact date/locale/category and create an experiment hypothesis. Prefer user-owned exports before paid feeds.

Acceptance:

- Show provider, date, licensed scope, estimated versus observed data and missing coverage.
- Library presence does not prove ad performance or authorize reuse; existing rights and viral thresholds remain.
- Stale/incomparable observations cannot become winning claims; preserve links into the hypothesis.

Status: REQUIRED_NOT_COMPLETE.

### MW-07 - Previewed reusable CSV/JSON evidence intake (P0)

PARTIAL: typed imports and snapshots exist; provider-export mapping preview is missing.

Workflow: Share bounded mapping preview, row validation, duplicate review and atomic import across attribution, costs, lifecycle and competitor evidence; save noncredential mapping templates.

Acceptance:

- Reject bad schemas, duplicate columns/keys, oversized files/rows/depth and formula injection on spreadsheet export.
- Failed import preserves prior data; credentials and reusable authority cannot be imported.
- Retain app scope, source hash, mapping version, units and coverage; replay is idempotent.

Status: REQUIRED_NOT_COMPLETE.

### MW-08 - Verified event to prioritized review task (P1)

PARTIAL: signed payment/StoreKit/attribution intake exists; marketing review rules are missing.

Workflow: Turn verified imported/provider events or mature metric thresholds into deduplicated tasks with evidence, reason and next action. Support dry-run, pause, threshold edits and links to telemetry/history.

Acceptance:

- Test authentication/signature failure, stale/duplicate/late delivery, cooldown and recovery.
- Decline rules require baseline, window, maturity and sample; missing data cannot manufacture a decline.
- Events prepare tasks only; no implicit publication, spend, external message or public server exposure.

Status: REQUIRED_NOT_COMPLETE.

## Shared UX and engineering requirements

- Human and agent parity through existing UI/CLI/MCP contracts.
- Plain-language purpose, inputs, delivered result and next action with progressive disclosure.
- Observed versus unavailable metrics, active progress, actionable recovery and source-linked history.
- Analytics and PDF/data export for each implemented workflow using existing privacy boundaries.
- Exact human or already-authorized standing scope for effects; imports never grant credentials or authority.
- Reuse domain stores and bounded adapters; measure before claiming speed or savings.

## Delivery order

MW-07 -> MW-02 -> MW-03 -> MW-01 -> MW-04 -> MW-05 -> MW-08 -> MW-06

Select native provider implementation by actual user need and permitted access. CSV/JSON is a reusable delivery path, not a waiver of complete workflow acceptance.
Verify current provider schemas, permissions and endpoint support from official sources before implementation. No paid-feed purchase is authorized.

## Deferred from this report addition

- Blanket integration of every named MMP, CRM, ad network or intelligence vendor.
- Duplicate Apple connectors, schedulers, attribution stores or creative libraries.
- Unlicensed scraping, inferred ad performance, automatic spend and unapproved external delivery.

This review does not implement these workflows or prove live provider/device acceptance.
Acceptance matrix and reviewed source hashes: specs/wmm-marketer-gap-review.json.
