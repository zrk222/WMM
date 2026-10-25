# Spec: drive-media-import
Status: implementation; full user/agent media integration remains incomplete
Parent: specs/drive-media-workflow.md T4

## MUST - Functional core
### Requirements (EARS)
- The system shall reject `drive_import_scope` for files up to 64 MiB unless an exact app-owned confirmed connection identity/version and current manifest authorize the requested file among at most 24 selected identities, with live protected access and a current verified requesting account before provider metadata or media download.
- The system shall return `drive_blob_metadata` only for a selected downloadable nontrashed MP4, MOV or WebM blob from a fixed Google Drive file endpoint, with exact identity, decimal version, matching filename suffix, declared size from 1 to 67108864 bytes and a valid MD5 content checksum, rejecting documents, redirects or unsupported fields before download.
- The system shall download `drive_blob_bytes` through fixed Google GET requests with redirects disabled, 15 seconds socket timeout, at most 65536 bytes per read and a 120 seconds observed read budget, rejecting over-limit, truncated or checksum-mismatched content and preserving exact original bytes without using supplied URLs.
- The system shall reject `drive_changed_source` if metadata/version/content identity, requesting account, connection revision, manifest, expiry or cancellation changes during download, native validation or commit, verifying metadata and requesting account again after the original bytes are received.
- The system shall store `drive_managed_import` through the existing decoded managed-media validator with unchanged 64 MiB and 60 seconds video bounds, retaining exact Google account/file/version/MD5/connection provenance and source SHA256 as immutable media, starting with UNKNOWN reuse permission and requiring separate owner review before rendering.
- The system shall return `drive_import_replay` for an identical source/provenance/body request key without creating duplicate media, reject changed provider provenance or bytes under the same key, and preserve existing local-upload behavior and upload-body restrictions.
- The system shall emit `drive_import_proof` using actual synthetic video bytes, provider/native seams and isolated SQL, proving original playback/hash, provenance, owner reuse, subsequent editor selection, scoped denial, changed source, disconnect during read and duplicate request behavior without claiming live Google acceptance.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_import_scope
  Given a confirmed app-owned account and selected identities
  When `drive_import_scope` requests an unselected foreign stale or expired file
  Then no media download is admitted
Scenario: drive_blob_metadata
  Given selected provider metadata
  When `drive_blob_metadata` checks content size type version and download capability
  Then only the exact bounded video blob is accepted
Scenario: drive_blob_bytes
  Given bounded synthetic content through the fixed provider seam
  When `drive_blob_bytes` streams the selected original
  Then exact bytes and checksum agree and truncation or overflow is rejected
Scenario: drive_changed_source
  Given a permitted in-flight download
  When `drive_changed_source` observes changed file account or local authority
  Then the original is not committed to the media library
Scenario: drive_managed_import
  Given verified original video bytes
  When `drive_managed_import` performs native validation and commit
  Then the immutable source includes provider provenance and UNKNOWN reuse permission
Scenario: drive_import_replay
  Given an existing original and request key
  When `drive_import_replay` receives identical or changed provenance
  Then identical import is deduplicated and changed provenance is denied
Scenario: drive_import_proof
  Given isolated imported original fixtures
  When `drive_import_proof` reviews and selects the source for editing
  Then source hash rights and provenance remain bound without a real provider request
```

## Official input checked 2026-10-25
https://developers.google.com/workspace/drive/api/guides/manage-downloads
Google documents files.get with alt=media for blob content and requires checking
capabilities.canDownload. Workspace documents and Google Vids use other flows;
they are not treated as MP4 blobs. A selected-file grant is not adaptation rights.

## WON'T - Out of scope
No broad Drive search, supplied download URL, redirects, provider writes, document
export or opaque unsupported download. UI/HTTP/CLI/MCP wiring, durable import jobs,
refresh leases, autonomous library scopes, full editor controls, telemetry/reports
and real Google acceptance remain required. No production or publication claim.
