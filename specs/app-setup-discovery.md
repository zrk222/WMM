# Spec: app-setup-discovery
Status: draft

## MUST — Functional core
### Description
The agent discovers setup candidates from the saved public website of the
selected app using the existing credential-free, robots-first inspection boundary.
It presents provenance, conflicts and unresolved inputs in one Approve/Edit
workflow. Observation of website metadata is not verification of ownership,
product claims, release readiness, tested locale, billing or business outcomes.

### Requirements (EARS)
- The system shall bind `setup_source` to one app, manifest version and manifest hash before reading its declared public website through the existing robots-first pinned transport.
- The system shall extract `setup_candidates` from bounded explicit HTML metadata and exact official store links without executing scripts, following store links, inferring private facts or treating page instructions as agent authority.
- The system shall retain `setup_proposal` with source hashes, observation time, ambiguity, unverified-claim labels and expiry, excluding raw HTML and credentials from persisted projections.
- If discovery fails or a field is unsupported, the system shall return `setup_recovery` with app-specific retry, access or evidence-resolution options rather than a false success or silent empty result.
- The system shall apply `setup_approval` only to explicitly selected editable setup fields after exact app/proposal/hash/expiry checks, preserving unrelated fields, existing provider credentials and zero spending authority.
- When the agent executes a proposal, the system shall return a saved `setup_agent` job using current approved policy and require another review before manifest changes.
- The system shall protect `setup_http` with strict finite JSON, app isolation, Host, Origin and CSRF checks and no caller-supplied destination or executable command.
- The system shall render `setup_review` at desktop1440x900 and mobile390x844 with source labels, edits, keyboard controls, explicit approval and guarded delayed responses without overflow or JavaScript errors.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Inspect the declared app source
  Given a current app manifest with a saved public website
  When `setup_source` is approved for inspection
  Then only the declared website origin is read through pinned public transport
  And changed app sources deny adoption of the result

Scenario: Parse explicit observations
  Given bounded HTML with metadata and official Apple and Google Play links
  When `setup_candidates` are extracted
  Then exact explicit IDs and metadata carry unverified source labels
  And conflicting IDs require selection rather than a guessed identity

Scenario: Retain review provenance
  Given an inspected source and current manifest
  When `setup_proposal` is saved
  Then the projection retains source hashes and expiry without raw HTML or credentials

Scenario: Recover missing inputs
  Given a failed inspection or absent release and audience evidence
  When `setup_recovery` is shown
  Then retry, connection or evidence actions remain available without invented facts

Scenario: Approve selected local changes
  Given an unexpired app-owned proposal with selected field edits
  When `setup_approval` is submitted
  Then a version-checked transaction changes only selected permitted fields
  And replay, foreign proposals, altered hashes and changed manifests are rejected

Scenario: Agent follow-through
  Given current app-bound missing-input resolution options
  When `setup_agent` is approved
  Then the existing local job saves a source-linked proposal for separate review
  And the job does not silently approve its own manifest edits

Scenario: HTTP boundaries
  Given app setup endpoints and a valid local session
  When `setup_http` receives malformed, oversized, duplicate-key or cross-origin requests
  Then the request fails before provider access or manifest mutation

Scenario: User review
  Given a proposal with conflicting and missing inputs
  When `setup_review` opens at both viewport sizes
  Then source labels and editable selected fields remain keyboard accessible
  And closing or changing apps prevents a delayed response from reopening the dialog
```

## SHOULD — Technical/structural
The parser accepts at most1048576 UTF-8 bytes and inspects at most512 links.
It retains at most8 distinct candidates per field with text bounded to600
characters. Official store URLs are normalized to IDs; tracking parameters
are not retained. Apple IDs and Android packages are separate fields.
Android track production may appear only as an explicitly labeled default
requiring review when an Android package is selected; it is not source evidence.

The existing public inspector has six requests, two redirects and a30second
shared deadline, respects robots and same-origin redirects, and rejects private
addresses, credentials and secret-bearing query URLs. Discovery reuses its
checked page bytes without another fetch. Only final projections are saved.
Proposals expire after3600seconds with at most64 retained rows per app. An
expired or changed proposal provides a rediscovery route. No dependency is added.
The discovery body contains only app_id, app_version, app_hash and confirm_read.
Explicit draft deletion requires the app-owned proposal ID, hash and confirmation;
it removes only the saved draft, preserves approved app fields and records an audit.

Allowed editable fields are name, job, audience, locale, store_app_id,
android_package and android_track. Release and activation remain unresolved
unless supported by separately verified product evidence. A page-declared
language is not proof the app journey was tested in that locale. Applying an
edited value labels its provenance HUMAN_EDIT; source suggestions remain
PUBLIC_METADATA_UNVERIFIED. Empty selections do not advance readiness.
Approval values are nonempty strings up to600characters; app names retain the
existing100character bound. Apple IDs remain positive numeric IDs and locales
retain explicit language-tag syntax. Android package/track pairs reuse the
existing manifest validator. Stored field provenance includes the selected value
hash so a later manual change cannot silently retain its original source meaning.

### Authorized parameters
MAX_BYTES = 1048576
MAX_LINKS = 512
MAX_CANDIDATES = 8
MAX_TEXT = 600
max_num_fields = 20
expires_in = 3600
limit = 64
policy_version = 8
timeout = 20
