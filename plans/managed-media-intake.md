# Plan: managed-media-intake
Spec: specs/managed-media-intake.md
Architect verdict: PASS - scoped app-owned bytes and owner-attestation records; derivative reuse stays blocked by default until a current review.

## Architecture
`Media(store)` validates the exact app manifest before invoking the existing
bytes-only validator. It stores validated source bytes under a generated,
app-digested private directory and commits one hash-bound SQLite row under the
same app-version check. App-scoped request keys make retry behavior deterministic.
Owner reviews append separate versions; only the latest current ALLOWED
attestation enables default `resolve`. Public records omit raw bytes, local
paths, storage names, and raw request keys. The HTTP adapter, UI, editor, and
portable export remain later integration work.

## Atomic tasks
- [ ] T1 | slice=specs | files=specs/managed-media-intake.md,specs/managed-media-intake.ssat.yaml | verify=`specline strict managed-media-intake --root .; specline verify-validators managed-media-intake --root .; specline gate spec managed-media-intake --root .; specline gate plan managed-media-intake --root .` | Lock app scope, storage/review contracts, and non-goals before code.
- [ ] T2 | slice=mission_control | files=mission_control/db.py,mission_control/managed_media_store.py,tests/test_managed_media_store.py | verify=`python -m unittest tests.test_managed_media_store -q` | Add tables, exact-manifest upload, private exclusive bytes, hash-bound metadata, safe read/list, and idempotent/concurrent replay.
- [ ] T3 | slice=mission_control | files=mission_control/managed_media_store.py,tests/test_managed_media_store.py | verify=`python -m unittest tests.test_managed_media_store -q` | Add OWNER-checked append-only attestation, stale/revocation states, and fail-closed default resolve.
- [ ] T4 | slice=smoke | files=smoke/managed-media-intake.json | verify=`forge verify-tests managed-media-intake specs/managed-media-intake.ssat.yaml --root .; forge smoke managed-media-intake --root .` | Exercise one generated local video-plus-audio file through the actual validator, SQLite round trip, owner review, and hash-verified resolve.
- [ ] T5 | slice=.factory/managed-media-intake | files=.factory/managed-media-intake/contract.json,.factory/managed-media-intake/observations.json,.factory/managed-media-intake/scope-review.md | verify=`factory audit workflows --root . --contract .factory/managed-media-intake/contract.json --observations .factory/managed-media-intake/observations.json --json` | Bind focused test, native smoke, reviewed scope exclusions, current source hashes, and explicit integration limits.

## Gates
CF doctor; strict spec, deleted/inverted requirement validators, and atomic plan;
focused behavioral tests; forced failure and symlink/reparse checks; mutation
evidence for wrong app/hash, changed idempotency payload, stale OWNER/version,
revocation and missing review; non-hollow real-byte smoke; scoped Factory
architecture/review gates; and a private workflow audit. Do not claim end-to-end
UGC intake, editor integration, rights verification, stitching, or release.
