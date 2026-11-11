# Spec: observational-campaign-tracking
Status: approved
SpecFactor-target: 0.75–2.5

## MUST — Functional core
### Description
Register one organic post as a one-arm **OBSERVATIONAL** attribution study; create its canonical tagged URL; ingest private observed events; and report tagged landing and linked registration counts with coverage and unknowns. This is attribution feasibility only, not campaign lift.

### User roles
- Verified owner: registers study, reads/assesses, corrects source records; publication stays in existing separate campaign flow.
- Scoped agent: performs only granted register/link/ingest/report/history/correct actions through the same service; cannot widen grants or approve publication.
- Human UI user: performs the same domain operations through WMM owner UI.

### Requirements (EARS)
- The system shall apply `immutable_schema=wmm.observational-campaign.v1` and store an immutable `wmm.observational-campaign.v1` study bound to app ID, current app version/release, study UUID, definition hash, registration time, source and fixed UTC window.
- When registering, the system shall apply `registration_lead_seconds=1;maximum_study_days=30` and require `starts_at` at least 1 second after `registered_at`, `ends_at` after `starts_at`, and a window duration no greater than 30 days; the registration schema shall omit baseline, MDE, allocation, sample size, second arm, install count, and lift decision.
- The system shall apply `canonical_utm_keys=utm_source,utm_medium,utm_campaign,utm_content` and accept only the configured app registered `HTTPS` website origin and a landing path on that same origin. It shall create the canonical URL with exactly 4 query keys: `utm_source` from `facebook|instagram|tiktok|youtube`, `utm_medium=organic`, `utm_campaign` equal to registered `study_id`, and `utm_content` equal to registered source/creative ID. Each ID shall match ASCII `[A-Za-z0-9_-]{1,128}`. The URL builder shall reject any other query key, host, contact data, or free-form URL.
- If the app version/release, website origin, study definition, or fixed window changes, the system shall apply `definition_drift=REJECT` and reject use of that study and require a newly registered study UUID. A study UUID may be registered only once per app.
- When ingesting a batch, the system shall apply `maximum_batch_events=500;source_coverage=EXPLICIT` and require private authenticated owner or current scoped-agent authority and exactly: `batch_id` UUID, `study_id`, `study_hash`, `app_version`, `source_id` ASCII `[A-Za-z0-9_-]{1,64}`, `source_receipt_sha256` (64 lowercase hex), `observed_at` aware timestamp, and `coverage` containing one `{complete:boolean, source_event_count: nonnegative integer|null}` record for each event type. It shall also require `events` with 0–500 entries. Empty arrays are valid; an empty array shall not imply zero activity when coverage is incomplete or null.
- When a study declares `collector_source_id`, the system shall pin that opaque, non-secret analytics collector in the immutable definition separately from the social channel. An import from another collector shall be rejected without writes. Older definitions without a collector remain readable and cannot enter descriptive-ready state.
- A descriptive checkpoint shall require a closed study window and the declared collector's latest source-reported receipt for each event type observed at or after close, with complete coverage and a source total matching the effective stored rows. Before close or with missing, early or inconsistent receipts, counts remain provisional and no ratio is shown. Complete zero is distinct from missing, and a zero landing denominator has no rate.
- The system shall apply `event_vocabulary=LANDING,REGISTRATION` and accept each event only when it contains exactly `event_id` and `subject_id` ASCII `[A-Za-z0-9_-]{1,128}`, `type`=`LANDING|REGISTRATION`, aware `occurred_at` normalized to UTC, `campaign_token` UUID or null, `consent` in `GRANTED`, `DENIED`, `UNKNOWN`, `bot`=true|false|null, and `internal_test` boolean. The event validator shall reject unsupported fields and raw personal identifiers. A false `bot` value means the source did not classify the event as a bot; it does not prove a human.
- The system shall apply `event_time_rule=STUDY_WINDOW_AND_SOURCE_OBSERVATION` and store events only when study/source/app-version/hash match and `occurred_at` <= `observed_at` and falls within the fixed study window. The system shall store `received_at` separately from `occurred_at`; it shall not replace event time with receipt time. A registration qualifies only when an eligible same-subject tagged landing with an earlier `occurred_at` exists by report `as_of`.
- When a batch contains 1–500 events, the system shall apply `collision_policy=ATOMIC_REJECT_WITH_EXACT_REUSE` and write the batch atomically. An exact repeated batch ID and payload hash shall return the stored receipt; a batch ID with a different hash shall fail without writes. The system shall count repeated event IDs with identical content once and reject the full batch if any event ID has different content, study, or source. The correction action shall append one record referencing original event ID/hash, replacement payload, reason, author, and timestamp; original payload and receipt shall remain readable.
- The system shall apply `unknown_policy=PRESERVE_NULL_AND_EXCLUSIONS` and return explicit exclusion counts for denied/unknown consent, bot true/null, internal tests, missing/invalid token, unmatched registration, and duplicate records. The system shall return unknown source coverage as null and shall not infer an eligible event from an excluded or unknown record.
- When assessed, the system shall apply `report_unit=DISTINCT_PSEUDONYMOUS_SUBJECT` and return distinct-subject counts for eligible tagged landings and registrations linked to an earlier eligible landing, exclusions/unknowns by reason, source coverage (including whether an empty source response was complete), event/receipt hashes, app version, study window and UTC as-of time. If no eligible observation exists, counts are null unless the source supplied complete coverage for that event type, in which case observed zero is explicit.
- The system shall apply `report_scope=ATTRIBUTED_DESCRIPTIVE_ONLY` and return every report with label `ATTRIBUTED_DESCRIPTIVE_ONLY` and omit install, activation, paid-conversion, revenue, lift-interval, winner, and causal-decision fields. The report handler shall exclude assignment/exposure signals from landing and registration counts and shall not emit human-view claims.
- The system shall apply `surface_policy=SHARED_DOMAIN_HANDLER` and provide six domain actions: register, tagged URL, ingest, report, history, correct. UI, `CLI`, `MCP` and agent workflows shall call the same shared handler and return the same schema, validation errors, authorization result and receipts. No public ingestion endpoint shall be added.
- The system shall apply `authorization_policy=CURRENT_SCOPED_GRANT_OR_OWNER` and publish each action, its exact input schema, app scope, grant requirement, and order in the operation catalog and agent workflow/manifest. The authorization handler shall reject an agent request without a current matching grant; the observational workflow shall not expose owner confirmation or publication actions.
- When importing WizeMe evidence, the system shall apply `attribution_policy=SOURCE_REPORTED_FIRST_TOUCH` and map the existing UTM acquisition and first-party analytics fields through the private authenticated collector; it shall not add an SDK or public collector. The importer shall preserve first-touch attribution and flag a returned visit with an earlier source as not newly acquired without source/session linkage. Local acceptance shall not claim deployment or live link-to-registration roundtrip.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Register the bounded canonical link
  Given an authenticated owner, current app website origin, supported utm_source, and opaque source/creative ID
  When a study is registered before its future start with an end no more than 30 days after start
  Then WMM stores one immutable app/version/release/hash-bound study UUID
  And returns a same-origin HTTPS URL with exactly 4 query keys: utm_source, utm_medium=organic, utm_campaign equal to study UUID, and utm_content equal to source/creative ID
  And stores no baseline, second arm, sample size, or lift rule

Scenario: Reject host and time expansion
  Given a study using the configured app registered HTTPS origin and a 30-day maximum window
  When registration supplies another origin, a past start, or an end more than 30 days after start
  Then registration fails with no study or URL receipt written

Scenario: Count linked descriptive observations
  Given complete source coverage and one GRANTED, non-test, non-bot-classified tagged landing at time T
  When one same-subject registration with the same campaign token occurs after T and within the fixed window
  Then report distinct landing=1 and linked registration=1 with source receipt hash and explicit UTC as-of
  And label the report ATTRIBUTED_DESCRIPTIVE_ONLY with no lift or install claim

Scenario: Preserve exclusions and unknowns
  Given events with denied/unknown consent, bot true/null, internal_test true, absent/invalid token, or no prior landing
  When a report is assessed
  Then each is represented under its explicit exclusion/unknown reason
  And none is counted as an eligible landing or registration

Scenario: Distinguish unknown from complete zero
  Given no events for a source and event type
  When source coverage is absent or incomplete
  Then that event count is null
  When the source receipt declares complete coverage and zero matching events
  Then the report returns observed zero with that receipt and coverage state

Scenario: Enforce atomic retries and corrections
  Given an existing batch and event ID with canonical payload hash H
  When the same batch/hash is retried
  Then the prior receipt is returned and counts do not change
  When either ID is reused with different content
  Then the whole batch fails with no partial write
  When a correction is accepted
  Then it appends a reasoned reference to the original hash and retains the original record

Scenario: Keep assignment and exposure separate
  Given assignment or exposure events are present in source evidence
  When campaign report is generated
  Then neither contributes to landing/registration counts or human-view claims

Scenario: Enforce identical surface semantics
  Given equivalent requests authorized through owner UI, command line interface (CLI), Model Context Protocol (MCP), or agent workflow
  When each action reaches the shared domain handler
  Then schemas, app scope, grant checks, deduplication, receipts, and result schema match

Scenario: Keep every declared invariant in the executable acceptance contract
  Given current app-owned source evidence
  When the domain acceptance suite exercises the declared contract
  And the accepted contract retains `immutable_schema=wmm.observational-campaign.v1`
  And the accepted contract retains `registration_lead_seconds=1;maximum_study_days=30`
  And the accepted contract retains `canonical_utm_keys=utm_source,utm_medium,utm_campaign,utm_content`
  And the accepted contract retains `definition_drift=REJECT`
  And the accepted contract retains `maximum_batch_events=500;source_coverage=EXPLICIT`
  And the accepted contract retains `event_vocabulary=LANDING,REGISTRATION`
  And the accepted contract retains `event_time_rule=STUDY_WINDOW_AND_SOURCE_OBSERVATION`
  And the accepted contract retains `collision_policy=ATOMIC_REJECT_WITH_EXACT_REUSE`
  And the accepted contract retains `unknown_policy=PRESERVE_NULL_AND_EXCLUSIONS`
  And the accepted contract retains `report_unit=DISTINCT_PSEUDONYMOUS_SUBJECT`
  And the accepted contract retains `report_scope=ATTRIBUTED_DESCRIPTIVE_ONLY`
  And the accepted contract retains `surface_policy=SHARED_DOMAIN_HANDLER`
  And the accepted contract retains `authorization_policy=CURRENT_SCOPED_GRANT_OR_OWNER`
  And the accepted contract retains `attribution_policy=SOURCE_REPORTED_FIRST_TOUCH`
  Then all declared invariants match the registered study and its report
```

## SHOULD — Technical/structural
- ADR references: add only if selected storage/authority materially departs from existing app-local record and ledger conventions.
- Study schema: `{schema, study_id, app_id, app_version, release, origin, landing_path, utm_source, utm_medium, utm_campaign, utm_content, starts_at, ends_at, source, registered_at, definition_hash}`. Hash is over canonical definition excluding the hash field.
- Batch schema: exact fields specified above; event set is closed. Event identity is unique within app/source/event ID. Batch receipts bind canonical payload hash, study hash, source receipt hash, app version, and accepted/rejected status.
- Report schema: `growth.observational-campaign-report.v1`; counts are nullable integers with separate `coverage_complete` booleans and reason arrays. The additive checkpoint exposes numerator and denominator only when descriptive review is ready and eligible landings are positive. The UI and private PDF may display the descriptive registration rate from these counts; no interval, lift or winner field.
- Existing `ledger.py` is not a fit as-is: its events omit landing/registration and campaign token/consent/bot/test status; funnel denominator is INSTALL; report completeness requires maturity and cost records. Reuse app scoping, canonical hashes, append-only audit and transaction/collision patterns where safe, not its funnel estimator or comparative analyzer.
- Expose six closed operations as `/api/apps/{app}/observational-campaigns` private loopback routes and matching CLI/MCP/catalog names. Implement a shared service handler. Update `agent_workflow_protocol`, manifest/automation requirements, catalog, CLI/MCP and owner UI. Require current grant checks per action; no new authority or provider effect.
- WizeMe source files `apps/web/src/lib/acquisition.ts`, `analytics.ts`, and `services/api/src/lib/acquisition-attribution.ts` are reported to implement UTM capture, first-touch storage, and first-party events. Validate exact payload mapping/consent/bot/dedup semantics against source before coding; keep raw customer data in WizeMe. Verify deployed link-to-registration roundtrip separately before any live result.

## SHOULD NOT — Implementation details
Do not create comparative arms, infer missing counts, fabricate denominators, overwrite first-touch, export customer identifiers, mutate provider state, publish from this study, or call attribution causal lift.
