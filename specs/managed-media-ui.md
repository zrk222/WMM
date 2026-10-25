# Spec: managed-media-ui
Status: draft

## MUST - Inspect owned local footage
### Requirements (EARS)
- The system shall send selected MP4 MOV or WebM files of at most 67108864 bytes each through `media_upload`.
- The system shall show original playback, decoded picture/audio metadata and source provenance through `media_inspect`.
- The system shall send source-bound owner reuse attestations and revocation with current review version and saved decision and permission basis selected on reopen through `media_rights`.
- The system shall reject stale app/version/identity/dialog responses and pause uncertain mutations without automatic resend through `media_scope`.
- The system shall return observed library counts and privacy-bounded printable and JSON reports through `media_report`.
- The system shall show readable keyboard and narrow-screen controls with actual status and recovery actions through `media_access`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: media_upload
  Given several selected local clips
  When `media_upload` submits them
  Then bounded files upload sequentially with distinct retained request identities
Scenario: media_inspect
  Given an imported clip
  When `media_inspect` opens
  Then original playback and decoded metadata appear without claiming reuse permission
Scenario: media_rights
  Given an owner review decision
  When `media_rights` submits
  Then current manifest review version and exact source hash bind the attestation
Scenario: media_scope
  Given an uncertain upload or changed app context
  When `media_scope` receives a reply
  Then no automatic resend or stale interface replacement occurs
Scenario: media_report
  Given a loaded media library
  When `media_report` exports
  Then only observed counts and metadata are included without review evidence or private paths
Scenario: media_access
  Given a keyboard user or narrow viewport
  When `media_access` navigates the workflow
  Then controls remain usable and completed or uncertain state has a clear next step
```

## Boundaries
Original footage remains preserved. Technical decoding and file access do not
establish derivative reuse rights. Reviews are operator attestations, not legal
verification. Optional Drive ingestion remains REQUIRED_NOT_COMPLETE; no inactive
connect button is presented. Shared timeline stitching/render/export integration
is parent work and is not established by this library UI.

## Authorized parameters
MAX_BYTES = 67108864
Review evidence is nonempty text of at most 1000 characters.
