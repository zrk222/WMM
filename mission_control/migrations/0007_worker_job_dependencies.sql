CREATE TABLE IF NOT EXISTS worker_job_dependencies (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    owner TEXT NOT NULL,
    owner_version INTEGER NOT NULL CHECK (owner_version > 0),
    bindings TEXT NOT NULL,
    bindings_sha256 TEXT NOT NULL CHECK (length(bindings_sha256) = 64),
    claimed_receipts TEXT,
    claimed_receipts_sha256 TEXT CHECK (
        length(claimed_receipts_sha256) = 64
    ),
    CHECK ((claimed_receipts IS NULL) = (claimed_receipts_sha256 IS NULL))
) WITHOUT ROWID;

CREATE TRIGGER IF NOT EXISTS worker_job_dependencies_no_rebind
BEFORE UPDATE OF job_id,owner,owner_version,bindings,bindings_sha256 ON worker_job_dependencies
BEGIN SELECT RAISE(ABORT,'job prerequisites are immutable'); END;

CREATE TRIGGER IF NOT EXISTS worker_job_dependencies_no_receipt_replacement
BEFORE UPDATE OF claimed_receipts,claimed_receipts_sha256 ON worker_job_dependencies
WHEN OLD.claimed_receipts IS NOT NULL
BEGIN SELECT RAISE(ABORT,'claimed job prerequisite receipts are immutable'); END;
