# Audit evidence bundle

Status: **evidence manifest, not an audit opinion**.

The bundle is a read-only snapshot of one app's database metadata, audit-chain digest, authority/session counts, and attribution links. It is intended to make an external review reproducible without exporting raw evidence or credentials.

## Export

```sh
python tools/audit_bundle.py export \
  --database <owner-private>/mission-control.sqlite3 \
  --app <app-id> \
  --out audit-<app-id>.json
```

## Verify

```sh
python tools/audit_bundle.py verify \
  --database <same database> \
  --app <app-id> \
  --bundle audit-<app-id>.json
```

Verification fails if:

- the bundle manifest hash does not match its contents;
- the database schema, app row, key-table digests, audit chain or attribution links no longer match;
- the app is missing or the app id is malformed.

## Contents

- database schema hash;
- app-scoped row counts and digests for key evidence/authority tables;
- audit row count, first/last IDs and a sequential SHA-256 chain over retained audit rows;
- observational study IDs/hashes, install batches and linked/unlinked campaign tokens;
- install state counts;
- explicit limitations.

## What it does not prove

- It is not an independent audit, SOC 2/ISO report or penetration test.
- It does not prove earlier history: the chain is computed over rows retained at export time.
- It does not prove provider entitlement, delivery, billing accuracy or marketing outcomes.
- It does not replace an external timestamp/WORM log sink.
- It does not authorize remote access, team hosting or commercial delivery.

Use it as input to an external security review; the reviewer still needs to inspect the running boundary and source.
