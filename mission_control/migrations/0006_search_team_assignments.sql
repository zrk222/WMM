CREATE TABLE IF NOT EXISTS search_team_assignments (
    app_id TEXT NOT NULL,
    review_hash TEXT NOT NULL,
    action_id TEXT NOT NULL,
    grant_id TEXT NOT NULL REFERENCES agent_grants(id),
    grant_version INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    assigned_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ASSIGNED','COMPLETED','NEEDS_EXTERNAL_VERIFICATION')),
    result TEXT,
    receipt_sha256 TEXT,
    PRIMARY KEY(app_id,review_hash,action_id),
    FOREIGN KEY(app_id,review_hash,action_id) REFERENCES search_store_action_receipts(app_id,review_hash,action_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS search_team_inbox ON search_team_assignments(grant_id,grant_version,app_id);
