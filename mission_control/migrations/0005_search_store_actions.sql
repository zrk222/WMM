CREATE TABLE IF NOT EXISTS search_store_action_receipts (
    app_id TEXT NOT NULL REFERENCES apps(id),
    review_hash TEXT NOT NULL,
    action_id TEXT NOT NULL,
    data TEXT NOT NULL,
    hash TEXT NOT NULL,
    PRIMARY KEY(app_id, review_hash, action_id)
) WITHOUT ROWID;
