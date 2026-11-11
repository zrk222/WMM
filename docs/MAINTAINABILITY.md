# WMM maintainability

Start with [Contributing](../CONTRIBUTING.md) for the reproduction and review
protocol. For current product boundaries, see [Release scope](../RELEASE-SCOPE.md).

| Area | Current approach | Next acceptance gate |
| --- | --- | --- |
| Readable code | Ruff and Prettier check the standing authority module and campaign monitor. | Expand by touched module, after focused behavior checks. Avoid mixing broad formatting changes with behavior changes. |
| Typed boundaries | Standing execution and worker lease context have explicit Python shapes. | Type the request and storage boundaries one at a time. Treat static typing and runtime validation as separate checks. |
| SQLite schema | Discovery and Apple Metrics DDL live in separate modules. Their assembled SQL and existing database behavior are unchanged. | Define an ordered, transactional migration ledger before the next schema migration. Test old, current and new workspaces, interrupted upgrades, backup restore and authority invariants. |
| HTTP server | The current loopback transport owns routing, sessions, request validation and write controls. | Compare a candidate adapter against the same route, origin, CSRF, session, OAuth and error tests. Measure request latency, startup and memory before choosing a framework or moving traffic. |
| Evidence and review | PRs record exact candidate SHA and review status. New or enlarged tracked evidence over 512 KiB is rejected. | Prove durable retrieval and hash replay before removing old tracked reports. Retire merged branches only after checking they are not referenced by open work or release evidence. A second human maintainer and their independent review are still pending. |

## Run the formatting checks

~~~sh
python -m pip install ruff==0.14.10
python -m ruff format --check mission_control/automation_execution.py tools/check_evidence_budget.py
python -m ruff check mission_control/automation_execution.py tools/check_evidence_budget.py
npx --yes prettier@3.6.2 --check mission_control/static/campaign-monitor.js
~~~

For a new gap, record the affected workflow, a reproducer and the acceptance
test in the owning spec or issue. A small formatting diff, green synthetic
tests or a saved agent receipt does not establish live provider behavior.

## Replay archived evidence

Eight large historical scan reports are indexed in
[archive-index.json](evidence/archive-index.json). A full Git clone and the
local Code Factory CLI can verify the exact original receipts:

~~~sh
python tools/replay_historical_evidence.py
~~~

The command reads immutable Git blobs, checks their size and SHA-256, and
runs the historical workflow verifier in disposable directories. It does
not regenerate scans, edit the current checkout, or certify current source.
A shallow clone must fetch the historical commits first. Report files are
still available in Git history; reducing the current checkout does not
rewrite history or reduce a full clone by the same amount.
