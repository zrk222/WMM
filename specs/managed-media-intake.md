# Spec: managed-media-intake
Status: approved

## MUST - App-owned immutable video intake

### Description
Store user-supplied video bytes privately under one existing WMM app, retain
technical validation evidence and append owner-supplied reuse attestations. This
slice is local storage and review state only. An owner attestation is not legal
verification or provider confirmation.

### Roles and authority
- An authenticated app caller supplies bytes to the local store service; a later
  HTTP adapter must authenticate the caller and authorize upload.
- Only a principal with a current active OWNER membership in the app may append a
  rights review. The store checks the database role and ignores role claims in
  the passed user object. The HTTP adapter handles fresh identity verification.
- A local renderer may receive a private path from `resolve` only after the
  default current-approval check. No HTTP response may serialize this path.

### Requirements (EARS)
- The system shall accept `media_envelope` uploads only when the body has exactly `manifest_version` and `request_key`, the app exists, the manifest version is a positive integer, and the request key is 1 through 120 UTF-8 bytes.
- The system shall enforce `media_bytes`: reject non-byte input, empty input, input above 67108864 bytes, or a filename suffix outside `.mp4`, `.mov`, and `.webm` before calling `managed_media_validation.inspect`.
- The system shall enforce `media_basename`: reject a normalized filename basename above 255 UTF-8 bytes, store only the cross-platform basename, and create media files as 32 lowercase hexadecimal characters plus the validated suffix beneath exactly `store.path.parent/managed-media/digest(app_id)`.
- The system shall enforce `media_initial_evidence`: store the exact SHA256, byte count, bounded metadata, decoded-frame evidence, upload provenance, original manifest version, and initial rights status `UNKNOWN` returned from `managed_media_validation.inspect`.
- When `media_replay` occurs, the same app-scoped request key has the same manifest version, normalized basename, source SHA256, and byte count, and the system shall return the previously committed media item without creating another file or database row.
- If `media_key_conflict` occurs, a committed app-scoped request key has a different request hash, the system shall reject the upload; an unused request key shall create a distinct media ID even when manifest version, basename, source SHA256, and byte count match an existing record.
- The system shall enforce `media_manifest_guard`: reject an upload unless its exact current manifest version matches both before video inspection and inside the `BEGIN IMMEDIATE` transaction that inserts the media row; write the supplied raw byte sequence unchanged.
- The system shall enforce `media_path_guard`: create each media file exclusively and reject symlinks, reparse points, or non-regular objects in the two managed-media directories or generated media file; each media file shall contain at most 67108864 bytes and remain exactly one file level beneath the app directory resolved under the database parent.
- The system shall enforce `media_hash_binding`: bind each media row hash to its app, media ID, canonical data, request key, request hash, and creation time; read and resolve shall reject changed rows, missing files, suffix mismatches, byte-count changes, and SHA256 mismatches.
- The system shall enforce `media_collection_limit`: return at most 1000 media items per app, reject an upload when the app already has 1000 retained items, and preserve all committed items.
- The system shall enforce `media_public_record`: return public list and read records without raw bytes, local paths, private storage names, or raw request keys; read returns a basename of at most 255 UTF-8 bytes, original SHA256, size, metadata, decoded evidence, provenance, current rights status, validated review history, and SHA256 of the UTF-8 upload request key.
- The system shall enforce `media_review_envelope`: accept a review only when its body has exactly `expected_version`, `manifest_version`, `source_sha256`, `status`, `basis`, and `evidence`, the current manifest version matches, and `source_sha256` equals the retained original bytes hash.
- The system shall enforce `media_owner_authority`: require the passed principal to have a current active OWNER role in the app before appending a review and reject a role supplied in the user object as authorization.
- The system shall enforce `media_review_history`: append review versions from 1 through 100 with statuses `ALLOWED` or `REVOKED`, bases `OWNED`, `LICENSED`, or `CONSENT`, and evidence text from 1 through 1000 characters; reject stale expected versions without changing review history.
- The system shall enforce `media_reuse_state`: mark reuse available only when the latest validated review is `ALLOWED`, its source hash and manifest version match the original asset and current app version, and its reviewer remains an active OWNER at the exact recorded role version; returned review data says `OPERATOR_SUPPLIED_NOT_EXTERNALLY_VERIFIED`.
- The system shall enforce `media_resolution_gate`: reject `resolve(..., require_reuse=True)` when the review is missing, stale, revoked, or bound to a different source hash; `require_reuse=False` permits inspection of verified original bytes without indicating derivative reuse approval.
- The system shall enforce `media_original_read`: within one database snapshot, require a current active app OWNER principal, verify a retained original from 1 through 67108864 bytes through one bounded file descriptor, and return the safe public item with exact hash-verified bytes while rejecting links, path escapes, size changes and digest mismatches.
- The system shall enforce `media_reviewer_role_binding`: when an ALLOWED reviewer loses active OWNER status or the recorded OWNER role version changes, return `rights_status=STALE`, `reuse_available=false`, and a bounded public reason while preserving every review version.
- The system shall enforce `media_review_append_only`: preserve each prior review version when a higher version is appended and never update or delete a committed review through this store API.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: media_envelope
  Given the exact upload body and an existing app
  When `media_envelope` validates a positive manifest version and bounded request key
  Then only that envelope is accepted

Scenario: media_bytes
  Given empty, oversized, non-byte, or unsupported-suffix input
  When `media_bytes` checks the input before inspection
  Then invalid bytes reject before native validation

Scenario: media_basename
  Given a path-like filename with a cross-platform basename
  When `media_basename` stores a valid filename
  Then storage uses only the basename and a generated one-level private file

Scenario: media_initial_evidence
  Given valid synthetic video bytes with mocked bounded inspection evidence
  When `media_initial_evidence` stores the inspected item
  Then hash, size, metadata, decoded evidence, provenance and UNKNOWN status are retained

Scenario: media_replay
  Given an existing app and one committed upload receipt
  When `media_replay` receives the same request key and content again
  Then both calls return the same ID and only one file and row exist

Scenario: media_key_conflict
  Given one request key already bound to an upload payload
  When `media_key_conflict` receives a changed payload or a distinct key with identical bytes
  Then changed reuse rejects and each unused key receives a distinct media ID

Scenario: media_manifest_guard
  Given an upload whose app version changes during video inspection
  When `media_manifest_guard` checks the version inside the insert transaction
  Then the upload rejects and no newly owned row or file remains

Scenario: media_path_guard
  Given a managed-media parent or generated file that is linked or outside the database parent
  When `media_path_guard` creates or verifies the source file
  Then the store rejects links and escaped paths

Scenario: media_hash_binding
  Given a retained row or source file whose bound bytes have changed
  When `media_hash_binding` reads or resolves the asset
  Then changed records, size, suffix or digest reject

Scenario: media_collection_limit
  Given an app with 1000 retained media items
  When `media_collection_limit` lists or receives another upload
  Then list remains bounded and the new upload rejects without deleting retained items

Scenario: media_public_record
  Given a retained source with review history and a private request key
  When `media_public_record` returns list and read data
  Then the record contains `upload_request_key_sha256` but no raw key, bytes, storage name or path

Scenario: media_review_envelope
  Given an exact review body bound to the current app and source hash
  When `media_review_envelope` validates the review input
  Then only the current manifest and retained source hash can be reviewed

Scenario: media_owner_authority
  Given a principal without active OWNER membership and a forged role claim in its user object
  When `media_owner_authority` attempts to append a review
  Then the store rejects the review based on current database membership

Scenario: media_review_history
  Given a current OWNER and an expected review version
  When `media_review_history` appends a bounded ALLOWED or REVOKED review
  Then valid versions append and stale versions leave history unchanged

Scenario: media_reuse_state
  Given the latest review matches the current manifest and source hash
  When `media_reuse_state` renders review status
  Then reuse is available only for ALLOWED and the record says `OPERATOR_SUPPLIED_NOT_EXTERNALLY_VERIFIED`

Scenario: media_resolution_gate
  Given a missing, stale, revoked, or mismatched review
  When `media_resolution_gate` resolves with reuse required
  Then resolution rejects while optional inspection still exposes no public path

Scenario: media_original_read
  Given an existing media item and current app OWNER principal
  When `media_original_read` returns the original file snapshot
  Then exact hash-verified bytes accompany a path-free public item and other principals reject

Scenario: media_reviewer_role_binding
  Given a current ALLOWED review bound to an OWNER principal and role version
  When `media_reviewer_role_binding` observes that role revoked or version changed
  Then reuse becomes STALE and unavailable while the attestation history remains intact

Scenario: media_review_append_only
  Given two appended review versions for one media item
  When `media_review_append_only` returns the review history
  Then both versions remain intact and no update or delete path is exposed
```

## SHOULD - Data model and API
- `managed_media`: `(app_id,id,data,hash,request_key,request_hash,created)`, primary key `(app_id,id)`, unique `(app_id,request_key)`.
- `managed_media_reviews`: `(app_id,media_id,version,data,hash,created)`, primary key `(app_id,media_id,version)`, foreign key `(app_id,media_id)` to `managed_media`.
- Public `rights_status` is `UNKNOWN`, `ALLOWED`, `REVOKED`, or `STALE`; `STALE` has bounded reason `SOURCE_OR_MANIFEST_CHANGED` or `REVIEWER_ROLE_CHANGED`, while `UNKNOWN` uses `NO_REVIEW`.
- `Media(store).upload(app_id, filename, raw, body, alive=lambda: None)` returns one public media item including `upload_request_key_sha256`; it never returns the raw request key.
- `Media(store).list(app_id)` returns `{items: [public media item]}`; `read(app_id, media_id)` returns one public item with review history.
- `review(app_id, media_id, body, user)` returns the public item after appending a current OWNER review; expected review version is zero when no review exists.
- `resolve(app_id, media_id, sha256, require_reuse=True)` returns a verified private local `Path` for internal callers only.
- `original(app_id, media_id, principal)` returns `(public_item, raw_bytes)` only after current OWNER verification and bounded exact-hash read; it never returns the private path.

## WON'T - Follow-up integration
- No HTTP route, upload UI, selected-source editor UI, project-source binding, stitching, export/backup portability, Drive/OAuth integration, provider call, download, or publication is included.
- No rights, consent, authorship, license validity, creative quality, or publication approval is established by an operator-supplied attestation.
- Synthetic inspection stubs do not prove native media validation; one smoke must exercise the installed FFmpeg/FFprobe validator on generated local video-plus-audio bytes.
