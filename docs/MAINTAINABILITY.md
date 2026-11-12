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

## JavaScript modules

The dashboard uses one native module entry, `dashboard.mjs`, without a build step.
Its 45 controller modules declare relative imports and exports. `app.mjs` owns
shared state and starts once, after the import graph initializes; controllers
never expose that state on `window`. Screen modules retain their existing duties.

`feature-apis.mjs` is the compatibility boundary for 27 existing feature libraries.
They retain CommonJS test exports and browser API objects; they are not claimed
as a complete library rewrite. Standalone callback pages retain their own scripts.
Add new dashboard dependencies explicitly, join `tools/maintained_js.txt`, and run
`node tools/check_es_modules.mjs`, ESLint and the browser flows. The graph check
is a static tripwire; actual Chromium linking and behavior are separate evidence.

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
python tools/check_format.py   # Ruff, Prettier, node --check and ESLint (app scripts)
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
agreement across the primary, backup and a fresh database. The nightly
workflow also builds the SBOM twice and compares the bytes. Binary
reproducibility of the PyInstaller bundle remains dependent on that toolchain.

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

## Automatic source enrollment

Before pushing, run `python tools/source_ratchet.py --base origin/main --write`.
Every changed or new Python/JavaScript file joins its existing maintained registry.
CI compares the exact reviewed base and candidate, rejecting missing enrollment
or registry shrinkage. Removed source remains as historical registry entries;
format/type runners check existing files. The checker never changes source.
Generated source receives no automatic exemption. Fix its generator when needed.

## SQLite writer reservation

Use `connection(path, write=True)` for a reviewed read/modify/write scope: it
reserves the writer lock with `BEGIN IMMEDIATE` before authority guards and
reads. Default read connections and existing manually declared transactions
retain their behavior. `busy_timeout_ms=0` preserves nonblocking lease heartbeats.
Nested declared writes are rejected before touching the caller's transaction.
Guards still run at entry and before commit; failure rolls back the owned scope.
SQLite `synchronous=FULL` (2) is deliberate and covered by connection tests.

The initial conversion covers 39 reviewed direct-write scopes, alongside the
existing manual transactions. Schema `executescript` and delegated transactions
retain their separately reviewed boundaries. This is not a claim that static
SQL classification proves the entire dynamic write call graph. Provider calls
must occur outside write transactions. Keep legacy connection isolation until
remaining callers have explicit, verified ownership; a global autocommit switch
would silently alter unconverted transaction behavior.

## Shrinkable parser properties

Install the test-only lock with `python -m pip install --require-hashes --only-binary :all: -r docs/requirements-properties.txt`.
Run `python -m unittest tests.test_parser_properties tests.test_property_profiles -v`.
The four parser property families use Hypothesis reuse/generate/shrink phases;
synthetic replay examples live only in `.factory/hypothesis/examples`. CI caches
are isolated by OS, Python, lock hash, PR/main namespace and shard. A missing
cache never prevents the tracked tests from running.

A discovered defect must receive a permanent named regression assertion in the
same fix PR. Cached examples and reproduction blobs supplement that assertion;
they never replace it. Keep the readable negative cases and do not filter out a
counterexample simply to pass. No real credentials, provider responses or customer
records belong in the example database.
