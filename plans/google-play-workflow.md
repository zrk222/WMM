# Plan: google-play-workflow
Spec: specs/google-play-workflow.md
Architect verdict: PASS

Architecture: reuse fixed-host providers transport, source-bound sync jobs,
app-isolated connection records and native Vault. Add typed Google Play contract,
bounded metadata discovery and read normalization first. Add native-loopback
PKCE consent with600second single-use state, protected verifier/refresh tokens,
manifest/connection version guards and candidate verification before replacement.
Integrate operation validation, collection recommendations, worker dispatch and
guided Connections UI. Preserve Apple and social contracts. No new dependency.
Keep each module below complexity10 using small typed helpers and explicit bounds.

- [x] T1 | slice=mission_control | files=mission_control/play_contract.py,mission_control/play_reports.py,tests/test_play_reports.py | verify=`python -m unittest tests.test_play_reports -q` | Implement exact targets, metadata discovery, fixed read destinations, provider state normalization and adversarial fixtures.
- [x] T2 | slice=mission_control | files=mission_control/play_auth.py,mission_control/play_connections.py,tests/test_play_connections.py | verify=`python -m unittest tests.test_play_connections -q` | Implement official consent and safe candidate replacement with protected tokens and single-use state.
- [x] T3 | slice=mission_control | files=mission_control/db.py,mission_control/credential_vault.py,tests/test_play_storage.py | verify=`python -m unittest tests.test_play_storage -q` | Persist flow lifecycle and protected credential isolation with expiry and cleanup recovery.
- [x] T4 | slice=mission_control | files=mission_control/providers.py,mission_control/provider_reports.py,mission_control/provider_auth.py,tests/test_play_worker.py | verify=`python -m unittest tests.test_play_worker -q` | Wire fixed source-bound queued reads and exact receipts.
- [x] T11 | slice=mission_control | files=mission_control/worker.py,tests/test_play_worker.py | verify=`python -m unittest tests.test_play_worker -q` | Reject missing or stale app/Android target scope before and after queued reads.
- [x] T5 | slice=mission_control | files=mission_control/service.py,mission_control/campaign_inputs.py,mission_control/marketing_agent_manifest.py,tests/test_play_collection.py | verify=`python -m unittest tests.test_play_collection -q` | Wire agent collection with stale and cancelled target denial.
- [x] T6 | slice=mission_control | files=mission_control/server.py,mission_control/static/index.html,mission_control/static/app.js,mission_control/static/google-play.js | verify=`python tools/test_play_browser.py` | Build guided discovery, approval, consent and reconnect controls through native route boundaries.
- [x] T12 | slice=mission_control | files=mission_control/play_http.py,mission_control/static/play-callback.html,mission_control/static/play-callback.js | verify=`python -m unittest tests.test_play_http -q` | Wire strict app-owned actions and a query-clearing local callback page with no external scripts.
- [x] T13 | slice=mission_control | files=mission_control/store.py,mission_control/play_contract.py,tests/test_play_manifest.py | verify=`python -m unittest tests.test_play_manifest -q` | Validate editable paired Android target fields without changing Apple identity or borrowing credentials; preserve portable snapshots while decomposing validation and export helpers to meet the existing complexity gate.
- [x] T7 | slice=tests | files=tests/test_play_http.py | verify=`python -m unittest tests.test_play_http -q` | Verify strict JSON, host, cross-origin and callback boundaries.
- [x] T8 | slice=tools | files=tools/test_play_browser.py | verify=`python tools/test_play_browser.py` | Verify desktop/mobile keyboard recovery, stale responses, errors and target identity.
- [x] T9 | slice=README.md | files=README.md | verify=`python tools/check_distribution.py` | Document actual setup and limits without advertising unverified live access.
- [x] T10 | slice=tests | files=tests/test_play_reports.py,tests/test_play_connections.py,tests/test_play_worker.py,tests/test_play_http.py | verify=`python -m unittest discover -s tests -q` | Verify all synthetic regressions before hash-bound workflow audit and release.
- [x] T14 | slice=smoke | files=smoke/play-connections-ui.json,smoke/play-read-integration.json | verify=`python -m unittest tests.test_play_http tests.test_play_worker tests.test_play_collection -q` | Declare actual HTTP and queued-read behavioral commands for anti-stub verification and smoke gates.

Release needs all tasks, strict SpecLine, source-scoped Forge gates, actual
desktop/mobile checks, deterministic Prestige audit, privacy check and hash-bound
workflow audit. Live OAuth and Play Console access remain separately observable;
synthetic receipts never establish a working connection to an operator's app.

T10 executed directly on the current candidate: 764 tests passed; exact output
retained in .factory/android-platform/full-regression-current.log. The workflow
audit must bind this log and candidate hashes; no redundant full-suite run is
needed merely to rewrite the task checkbox. Publication and owner activation
remain pending their release receipts, CI and private-instance verification.
