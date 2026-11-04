# Spec: organic-policy-owner-reads
Status: draft

## MUST - Functional core
### Description
Expose two bounded owner-only read services for the existing organic video policy, using current protected authority and existing evidence stores. Return current context candidates and immutable policy history without network access or writes.

### Requirements (EARS)
- When an exact protected owner `organic-video.policy-context` request with body `{}` is received, the system shall return current app version/hash, owner review binding, tested Facebook Page connections without credentials, current reusable sources with hashes/review versions, current approved claim text/IDs/hashes, completed Hypit output hashes and actionable missing states through `context`.
- When an exact protected owner `organic-video.policy-history` request with exact `{offset, request_id}` selectors is received, the system shall return deterministic pages of at most 100 owner policies with offset 0 through 2000 and exact bounded request ID matching through `history`.
- When a policy history item is returned, the system shall expose immutable ID/hash, request ID/hash, creation time, exact saved snapshot, revocation, expiry, app-current and owner-current flags, and `CURRENTNESS_NOT_REVALIDATED` for current rights/Page checks through `history_item`.
- When `usage` is rendered, the system shall derive generation counts from at most 500 reservations, artifact-slot counts from at most 20 admissions, and reserved-call counts from at most 500 calls, while separately reporting intent boundary-check units and provider phase completion from existing tables.
- If a stored policy, reservation or admission is corrupt or noncanonical, the system shall fail the read and not silently skip a row through `canonical_integrity`.
- If app, identity, owner role, request shape, pagination or evidence integrity is wrong, the system shall reject the read through `owner_scope`.
- The system shall perform no network access or writes and return no credentials, storage paths or raw diagnostics through `read_only_privacy`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: owner reads bounded current context and immutable policy history
  Given a current app owner and an exact protected operation
  When the owner reads context and requests policy history at offsets 0 and 100
  Then context contains only currently eligible evidence and safe Page metadata
  And history is deterministic, bounded, hash-validated, and marks rights/Page currentness as not revalidated
  And held reservations, admitted artifact slots, intent boundary-check units, provider phase completion, and remaining ceilings are separate counts
  And malformed, unauthorized, stale or tampered access is rejected without network or writes
```

## Constraints
Reuse `derivative_snapshot`, `bound_record`, `latest_proof`, `app_scope`, existing authority and existing policy tables. Add no tables, tools, engine behavior, mutation or provider capability. Tests use existing synthetic policy fixtures and temporary SQLite only.

## Authorized parameters
PAGE_SIZE = 100
MAX_OFFSET = 2000
