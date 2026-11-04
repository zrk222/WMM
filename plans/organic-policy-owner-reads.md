# Plan: organic-policy-owner-reads
Spec: specs/organic-policy-owner-reads.md
Architect verdict: PASS

## Scope
Implement `mission_control/organic_video_policy_ui.py` as pure read services called only after the HTTP layer establishes the exact fresh owner and protected operation. Keep HTTP routing and browser presentation in their separately owned files. Reuse existing policy tables, hashes, app scope, role authority, managed-media rights snapshots and brief proof validation. Do not add schema, mutation, credential access, network access, renderer behavior, provider effects or external tools.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/organic_video_policy_ui.py | verify=`python -m unittest tests.test_organic_video_policy_ui -v` | Implement exact protected owner checks, current context candidates and deterministic policy history with canonical hash checks, state flags, actual counts and safe remaining ceilings.
- [x] T2 | slice=tests | files=tests/test_organic_video_policy_ui.py | verify=`python -m unittest tests.test_organic_video_policy_ui -v` | Prove owner authority, exact outputs, hash/request reconciliation, stale/revoked/expired states, deterministic pagination, tamper rejection, and no-network behavior with the actual synthetic policy fixture.
- [x] T3 | slice=.factory/organic-video-automation/hypit | files=.factory/organic-video-automation/hypit/policy-owner-read-contract.json,.factory/organic-video-automation/hypit/policy-owner-read-observations.json,.factory/organic-video-automation/hypit/policy-owner-read-evidence.md | verify=`factory audit workflows --root . --contract .factory/workflow-audit-contract.json --observations .factory/workflow-audit-observations.json --json` | Bind candidate hashes and executable-profile observations to focused test output; preserve explicit exclusions with reviewed evidence and report any unavailable project-neutral gate.

## Proof
Use current Windows CPython + temporary SQLite + existing synthetic policy fixture; assert negative authority and tamper cases, no network, bounded deterministic paging, exact snapshot/hash fields, and source/Page currentness remains explicitly un-revalidated. Run the focused suite and applicable ECC verification (source audit/static check) without calling providers or adding dependencies.
