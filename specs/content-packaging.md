# Spec: content-packaging
Status: USER APPROVED / IMPLEMENTATION REQUIRED

## MUST - Functional core
### Requirements (EARS)
- The system shall store app-scoped packaging variants containing audience, app outcome, source references, title, thumbnail, opening frame, hook, CTA and app-proof references, bind each to the current app and creative revision and reject stale or foreign inputs, identified by `packaging_variants`.
- The system shall return neutral competitive-feed previews at 1440 pixels desktop and 390 pixels mobile widths with identical candidate/reference styling, optional hidden identity, reproducible randomized positions and actual title truncation for preview titles up to 300 characters, preserve draft status without fabricated view counts and label simulator observations separately from measured CTR, identified by `packaging_preview`.
- The system shall store a script-linked shot checklist for A-roll, B-roll, screen recordings, graphics and audio with source timestamps, asset identities, rights and claim-proof links; return missing assets and unsupported claims before production handoff, identified by `packaging_shots`.
- The system shall return user-selected YouTube channel or query collection through permitted sources with protected credentials, bounded request quotas, source identities, observation dates, failed reads and source-policy retention; reject API-derived outlier scoring until the applicable provider permission is recorded and verified, identified by `packaging_youtube`.
- The system shall return research filters from 1x through 20x separately from viral qualification, retain the mandatory 100000 views AND 10x documented comparable creator baseline, require at least 10 baseline posts drawn from up to 20 prior comparable posts, exclude the candidate, calculate qualification before display rounding and keep UGC intake exempt, identified by `packaging_outliers`.
- The system shall store owner-reviewed taste examples, exclusions, voice and visual rules, return script and platform cutdown proposals with source linkage, preserve editable timeline revisions and require current human or standing authority before execution, identified by `packaging_production`.
- The system shall return packaging-linked attention, app visits, installs, activation, trials, paid events and renewals only where source evidence and attribution identify each measure, preserve unknown denominators and return observed review time, rework and production cost separately from inferred savings in paginated reports of at most 1000 rows, identified by `packaging_learning`.
- The system shall return matching UI, CLI and MCP controls for packaging research, variants, preview evidence, shot lists, production handoff and results; retain upload and optional Drive intake, autonomous scope, live telemetry, cancellation, recovery and PDF/JSON/CSV reports, identified by `packaging_operations`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: packaging_variants
  Given current app and creative source hashes
  When `packaging_variants` stores a candidate and encounters changed source hashes
  Then the current candidate persists and stale or foreign writes reject
Scenario: packaging_preview
  Given candidate and reference assets
  When `packaging_preview` renders desktop and mobile comparisons
  Then styling is neutral and repeatable positions and draft status remain observable
Scenario: packaging_shots
  Given a script with linked claims and assets
  When `packaging_shots` resolves each planned shot
  Then missing assets rights and proof remain distinct from usable production inputs
Scenario: packaging_youtube
  Given user-authorized collection and a declared provider permission state
  When `packaging_youtube` collects permitted data or proposes API-derived scoring
  Then access failures and retention are tracked and unverified scoring permission blocks scoring
Scenario: packaging_outliers
  Given observed views and a documented comparable creator baseline
  When `packaging_outliers` evaluates research filters and viral qualification
  Then 100000 views AND 10x remain mandatory for viral qualification independently of research controls
Scenario: packaging_production
  Given owner-reviewed taste and current media evidence
  When `packaging_production` proposes scripts and platform cutdowns
  Then typed editor handoffs preserve source revisions and current execution authority
Scenario: packaging_learning
  Given observed creative results and app event evidence
  When `packaging_learning` presents performance and workflow costs
  Then supported attribution and unknowns remain visible without invented outcomes
Scenario: packaging_operations
  Given human and admitted agent operators
  When `packaging_operations` exercises authoring review execution recovery and reports
  Then the same current data and authority checks govern UI CLI and MCP
```

## Architecture and acceptance boundaries
Extend existing discovery collections, creative briefs, taste guidance, versioned editor/Hypit workflow, automation authority, telemetry, reports and app-sales ledger. Do not add a separate Streamlit runtime or replace the WMM application. YouTube is explicitly user-approved as a source and destination option. User approval is not evidence of Google approval for derived metrics, OAuth verification or additional API permissions. Record each provider gate independently. Refresh/delete API data according to its applicable source policy; immutable provenance must not imply indefinite retention of restricted API payloads. Caption downloads require the applicable video permissions. Do not use scraping as a permission bypass.

The 1x-20x research control never weakens viral-only eligibility. A public view counter, model rating or simulator result cannot prove that packaging caused performance, identify installs or establish revenue. Agent observations and inferred patterns are labeled interpretations. No fixed 50-percent performance claim, arbitrary production-time allocation, model throughput requirement or unverified tool API is adopted.

Native local production remains the first-class path, with optional configured BYOK services. Do not require a paid renderer, always-on ambient screen recording, automatic brand-rule mutation or third-party desktop editor. Preserve all earlier app-marketer controls and independent platform requirements. No ad spending, publication, production activation or external communication is authorized by this specification.

Full acceptance requires actual source collection where authorized, repeatable neutral previews, before/after creative renders, shot-to-asset and claim-proof readback, denied/stale/foreign/revoked paths, restart and uncertain-result recovery, human/agent parity, PDF/data reports and relevant native/device receipts. All are implementation obligations; this document proves none of their runtime outcomes.
