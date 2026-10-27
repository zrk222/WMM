# Apple Analytics T3 scope review

This slice adds offline parsing and SQLite reconciliation for supported Apple
App Downloads Standard report data. It changes no public or owner-facing UI,
keyboard flow, assistive-technology semantics, or visual output, so accessibility
checks are not applicable to this backend-only slice. It performs no provider
request, credential lookup, subprocess, publication, campaign launch, or other
external effect. The production ingestion function remains disabled until the
durable worker and authority fences are implemented; external-effects checks are
therefore not applicable here. The SQLite table is added idempotently through
the existing initializer and this change performs no backfill or destructive
data migration.
