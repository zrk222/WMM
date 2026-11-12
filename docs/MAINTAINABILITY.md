# WMM maintainability

Start with [Contributing](../CONTRIBUTING.md) for the reproduction and review
protocol. For current product boundaries, see [Release scope](../RELEASE-SCOPE.md).

| Area | Current approach | Next acceptance gate |
| --- | --- | --- |
| Readable code | Ruff formats and lints the maintained Python set after one behavior-preserving pass over all tracked Python; Prettier formats and checks all static JavaScript. | Keep the ratchet green; when UI scripts change, keep source-text tests whitespace-normalized instead of asserting exact formatting. |
| Typed boundaries | Generated TypedDict row shapes cover the core schema; Pyright checks the maintained Python allowlist. | Add request and storage boundary types one at a time. Static typing and runtime validation remain separate checks. |
| SQLite schema | An ordered transactional ledger (`mission_control/migrations/NNNN_*.sql`) records immutable checksums; every foreign-key child now has a leading index. | Add a new ordered file for every schema change; exercise old, current and new workspaces, interrupted upgrades and backup restore. |
| HTTP server | The loopback transport owns routing, sessions, request validation and write controls. Static assets revalidate by build-bound ETag while API responses stay `no-store`. | Compare a candidate adapter against the same route, origin, CSRF, session, OAuth and error tests before choosing a framework or moving traffic. |
| Evidence and review | PRs record the exact candidate SHA and review status. New or enlarged tracked evidence over 512 KiB is rejected; generated `.factory` evidence is untracked. | Prove durable retrieval and hash replay before removing old tracked reports. Retire merged branches only after checking they are not referenced by open work or release evidence. A second human maintainer and independent review are still pending. |

## Schema changes

The baseline is the idempotent assembled schema in `mission_control/db.py` plus
the host-installed `onesignal_setup` schema. Every later change is an ordered
file in `mission_control/migrations/NNNN_name.sql`.

- Files apply once each, in filename order, inside one transaction per file.
- `schema_migrations` records the baseline, name, SHA-256 checksum and time.
- Editing an applied migration fails startup; add a new migration instead.
- Existing databases without a ledger are adopted: the baseline is recorded and
  pending migrations are applied. Concurrent initializers recheck the ledger
  under the write lock, so each version applies once.
- `PRAGMA user_version` tracks the highest applied version.

## Foreign-key indexes

Every foreign-key child column must have a leading index. The migration and
`tests/test_migrations.py` coverage test enforce this: a new unindexed foreign
key fails the suite instead of creating an app-scoped table scan.

## Generated references

Regenerate and commit after a schema or catalog change:

```sh
python tools/generate_schema_types.py
python tools/generate_operation_docs.py
```

`mission_control/schema_types.py` provides TypedDict row shapes for the core
assembled schema. `docs/operation-catalog.md` gives every closed operation a
documented row. Both have `--check` modes used by CI.

## Ratchets

The maintained set is `tools/maintained_files.txt`. It may only grow: add a file
when you take ownership of its formatting and types.

```sh
python tools/check_format.py   # Ruff + Prettier checks on both maintained sets
python tools/check_types.py    # Pyright basic on maintained Python + row types
python tools/check_layering.py # import cycles, storage/portable/HTTP edges, docs rows
python tools/query_budget.py   # SQL statement budgets; --update only lowers
```

The `maintainability` CI job runs these plus the generated-reference and
integrity checks. `tools/query_budgets.json` holds the current budgets; lower a
budget only after proving the reduction, and never raise one silently.

## SQLite connection policy

`db.session` enables foreign keys, a 16 MiB page cache, in-memory temp storage
and a 256 MiB mmap limit. It deliberately leaves `synchronous` at the SQLite
default (`FULL`). Do not switch to `NORMAL` or `OFF` without an explicit owner
decision documented here: this product stores receipts whose last committed
transaction must survive power loss.

Verify the schema, backup and replay story with:

```sh
python tools/integrity_drill.py
```

That drill checks `PRAGMA integrity_check`, `foreign_key_check`, an online
backup/restore round trip, migration replay, `user_version` and schema-digest
agreement across the primary, backup and a fresh database. CI runs it nightly
and on each change.

## Repository hygiene

`.factory/`, `.forge/`, `.prestige/`, `.wrangler/` and `node_modules/` are
generated or dependency paths and must not be tracked. `check_distribution.py`
fails if one is. The hygiene workflow reports merged `codex/*` branches older
than seven days and deletes them only when manually requested.

## Run the checks

```sh
python -m pip install -r requirements.txt
python -m pip install --require-hashes -r docs/requirements-dev.txt
npm ci --ignore-scripts
python tools/check_format.py
python tools/check_types.py
python tools/check_layering.py
python tools/generate_schema_types.py --check
python tools/generate_operation_docs.py --check
python tools/query_budget.py
python tools/integrity_drill.py
```

For a new gap, record the affected workflow, a reproducer and the acceptance
test in the owning spec or issue. A small formatting diff, green synthetic
tests or a saved agent receipt does not establish live provider behavior.
