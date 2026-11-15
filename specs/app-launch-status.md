# iOS launch status and measurement eligibility

Reuse WMM's current App Store Connect binding. Read `appVersionState` first;
`appStoreState` is a deprecated fallback. These are version facts. A pending
update must not hide an older live version. A release-ready response alone
does not establish that the app is available in a storefront.

- The app-scoped projection defaults to `UNKNOWN`. Save each reading with
  source, observation time, storefront scope, evidence fingerprint, and the
  preceding status. Preserve older readings. An owner declaration stays
  unverified and never opens the paid-install path.
- Treat public listing results as scoped to the checked storefront. Verify the
  returned app identity. An empty lookup cannot prove non-submission, prior
  removal, or worldwide absence. Conflicting current sources yield `UNKNOWN`
  with both observations. TestFlight alone does not imply App Store availability.
- Confirm `LIVE` with current app-level Connect release evidence and exact
  storefront presence. Keep the first verified presence date distinct from an
  authoritative launch date; never invent a historical launch date.
- For known pre-launch periods, show store-dependent metrics as
  `NOT_APPLICABLE_YET`. Unknown availability stays unknown. Keep eligible web
  visits, registrations and other non-store observations; App Store availability
  does not establish whether web registration was possible during WizeMe E14.
- Offer pre-launch goals when live availability is unverified. Preserve existing
  budget, grant, and exact approval checks. Before any future install-optimized
  write, require fresh verified status for the approved storefront. Recheck
  status at dispatch and halt queued store-directed work on verified removal.
  Keep historical reports readable. Do not add an install-buying path here.
- Agents may read the app-scoped projection. Only a current authenticated owner
  may submit an unverified declaration; scoped grants cannot make that write.
  Never turn a status observation into a campaign permission.

Acceptance requires append-only history, source disagreement and staleness
fixtures, scoped read and denied agent-write tests, owner UI and report checks,
and authenticated Connect plus storefront readback. No Google Play expansion.

Sources: [Apple version state](https://developer.apple.com/documentation/appstoreconnectapi/appversionstate),
[App Store Connect 3.3](https://developer.apple.com/documentation/appstoreconnectapi/app-store-connect-api-3-3-release-notes),
[Apple public lookup](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/LookupExamples.html).
