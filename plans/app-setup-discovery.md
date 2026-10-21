# Plan: app-setup-discovery
Spec: specs/app-setup-discovery.md
Architect verdict: PASS

Use the current pinned public inspector, source-bound local records and typed
resolution jobs. Add a bounded projection parser and durable review proposals;
approval changes only explicitly selected manifest fields. Preserve Apple and
Google OAuth boundaries and current schemas. No external write or new dependency.

- [x] T1 | slice=mission_control | files=mission_control/setup_parse.py,tests/test_setup_parse.py | verify=`python -m unittest tests.test_setup_parse -q` | Extract bounded explicit metadata/store IDs with conflicts, safe provenance and no code execution.
- [x] T2 | slice=mission_control | files=mission_control/setup_discovery.py,mission_control/db.py,tests/test_setup_discovery.py | verify=`python -m unittest tests.test_setup_discovery -q` | Reuse robots-first checked bytes and persist exact source-bound expiring proposals and recovery.
- [x] T3 | slice=mission_control | files=mission_control/setup_approval.py,tests/test_setup_approval.py | verify=`python -m unittest tests.test_setup_approval -q` | Apply selected edits atomically with source/manifest/expiry/replay checks and provenance.
- [x] T4 | slice=mission_control | files=mission_control/setup_http.py,mission_control/server.py,mission_control/service.py,tests/test_setup_http.py | verify=`python -m unittest tests.test_setup_http -q` | Wire strict app-owned finite read/review/approval endpoints into the existing session boundary.
- [x] T5 | slice=mission_control | files=mission_control/static/setup-discovery.js,mission_control/static/app.js,mission_control/static/index.html,mission_control/static/automatic-preparation.js | verify=`python tools/test_setup_browser.py` | Build a source-linked Approve/Edit review and visible missing-input recovery with guarded async state.
- [x] T6 | slice=mission_control | files=mission_control/resolution_catalog.py,mission_control/resolution_plan.py,mission_control/resolution_tools.py,mission_control/marketing_agent_manifest.py | verify=`python -m unittest tests.test_setup_agent -q` | Add the typed policy-bound agent discovery option without automatic manifest approval.
- [x] T7 | slice=tests | files=tests/test_setup_agent.py | verify=`python -m unittest tests.test_setup_agent -q` | Verify approval scope, result links, stale/denied/cancelled jobs and source isolation.
- [x] T8 | slice=tools | files=tools/test_setup_browser.py | verify=`python tools/test_setup_browser.py` | Verify actual isolated desktop/mobile edit, approval, error recovery, keyboard and delayed-response behavior.
- [x] T9 | slice=README.md | files=README.md | verify=`python tools/check_distribution.py` | Document exact discovery/apply behavior and remaining evidence requirements.
- [x] T10 | slice=smoke | files=smoke/app-setup-discovery.json,smoke/app-setup-discovery-release.json,tests/test_sequence_plan.py,tests/test_sequence_runtime.py,tests/test_play_collection.py | verify=`python -m unittest discover -s tests -q` | Complete 805-test PASS is retained in .factory/setup-regression-current.log; 41 focused and 13 Node tests, desktop/mobile browser, anti-stub smoke, privacy and current gates pass. Exact hash-bound integrated receipt is required for release; owner activation remains separately verified.
