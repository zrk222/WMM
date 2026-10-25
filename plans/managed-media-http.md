# Plan: managed-media-http
Spec: specs/managed-media-http.md
Architect verdict: PASS

- [x] T1 | slice=mission_control | files=mission_control/managed_media_http.py,mission_control/server.py | verify=`python -m unittest tests.test_managed_media_http -q` | Implement media_owner, media_upload, media_original and media_commit using current protected owner scope.
- [x] T2 | slice=tests | files=tests/test_managed_media_http.py | verify=`python -m unittest tests.test_managed_media_http -q` | Prove exact headers, authority, original byte ranges, app isolation, upload and review over real synthetic loopback HTTP.

Use CF strict/validator gates, scoped native/storage/HTTP regressions, actual
browser upload/readback and privacy/hash-bound workflow evidence. Tests using
synthetic identity or decoder fixtures must identify those limits. No complete
stitching or real-provider acceptance claim follows from this transport slice.

Scoped implementation uses current protected owner scope, exact framing and
original captured bytes. Independent review passes20HTTP/storagetests and
three file-growth/corruption/replacement probes; the preview path-reopen finding
was fixed before acceptance. Root behavioral mutants detect removed canonical
path, removed commit-time owner guard and incorrect byte-range serving. Actual
browser/native intake acceptance remains a separate current-source check.
