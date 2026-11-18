CREATE TABLE IF NOT EXISTS apple_performance_refreshes (
    app_id TEXT NOT NULL REFERENCES apps(id),
    id TEXT NOT NULL,
    event_start TEXT NOT NULL,
    event_end TEXT NOT NULL,
    scope TEXT NOT NULL,
    scope_sha256 TEXT NOT NULL CHECK (length(scope_sha256) = 64),
    inventory_job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
    handoff_status TEXT,
    files TEXT,
    files_sha256 TEXT CHECK (length(files_sha256) = 64),
    created TEXT NOT NULL,
    PRIMARY KEY(app_id,id),
    CHECK ((handoff_status IS NULL) = (files IS NULL)),
    CHECK ((files IS NULL) = (files_sha256 IS NULL))
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS apple_performance_refreshes_window
ON apple_performance_refreshes(app_id,event_start,event_end,created DESC,id DESC);

CREATE TRIGGER IF NOT EXISTS apple_performance_refreshes_no_rebind
BEFORE UPDATE OF app_id,id,event_start,event_end,scope,scope_sha256,inventory_job_id,created
ON apple_performance_refreshes
BEGIN SELECT RAISE(ABORT,'Apple refresh authority is immutable'); END;

CREATE TRIGGER IF NOT EXISTS apple_performance_refreshes_no_second_handoff
BEFORE UPDATE OF handoff_status,files,files_sha256 ON apple_performance_refreshes
WHEN OLD.handoff_status IS NOT NULL
BEGIN SELECT RAISE(ABORT,'Apple refresh file handoff is immutable'); END;
