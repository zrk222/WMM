CREATE TABLE IF NOT EXISTS marketing_review_evidence (
 app_id TEXT NOT NULL REFERENCES apps(id), owner TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('ARTIFACT','EFFORT','DEMO','CHANGE','RETENTION')),
 id TEXT NOT NULL, scope_id TEXT NOT NULL, data TEXT NOT NULL,
 hash TEXT NOT NULL, created TEXT NOT NULL,
 PRIMARY KEY(app_id,owner,kind,id)
);
CREATE INDEX IF NOT EXISTS marketing_review_scope ON marketing_review_evidence(app_id,owner,scope_id,kind,created);
