# Spec: managed-media-http
Status: implementation

## MUST - Functional core
### Description
Connect app-owned UGC intake and reuse review to the local user interface without
changing existing native image upload or granting external publication authority.

### Requirements (EARS)
- The system shall reject media routes unless the raw path is the exact canonical app/media address, Host matches the loopback server, every supplied Origin matches that server and POST has exactly one Origin, the current session is freshly verified and its principal has current OWNER membership through `media_owner`; GET may omit Origin for native video playback.
- The system shall accept uploads only at media/uploads with one application/octet-stream Content-Type, no Transfer-Encoding, one decimal Content-Length from 1 through 67108864, one encoded X-Filename, one X-WMM-Manifest-Version and one X-WMM-Request-Key through `media_upload`; read the complete body within 5 seconds before app-owned validation and commit.
- The system shall return app-owned list/read/review records without private paths and serve original preview/download bytes with exact Range seeking through `media_original`; byte access shall not imply reuse approval.
- The system shall retain current owner/session authority at business-transaction entry and commit, and reject revocation or source/version mismatch through `media_commit`; review accepts only the documented app-owned attestation fields.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: media_owner
  Given a foreign app or stale owner session
  When `media_owner` handles a source request
  Then no source bytes or private metadata are returned
Scenario: media_upload
  Given duplicated headers or a truncated upload
  When `media_upload` reads its envelope
  Then the request rejects before native validation or media creation
Scenario: media_original
  Given a valid retained source and no reuse review
  When `media_original` returns a byte range
  Then the selected original bytes are served without granting derivative rights
Scenario: media_commit
  Given owner membership revoked while decoding
  When `media_commit` writes its transaction
  Then no asset row or retained file is committed
```

## WON'T - Out of scope
Drive OAuth, agent binary transport, editor source binding, actual stitching,
Hypit imported-media execution and publication remain separate required work.
