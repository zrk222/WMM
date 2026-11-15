CREATE TABLE IF NOT EXISTS automation_rule_runs (
    app_id TEXT NOT NULL REFERENCES apps(id),
    owner TEXT NOT NULL,
    id TEXT NOT NULL,
    app_version INTEGER NOT NULL,
    rule_version INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    receipt TEXT NOT NULL,
    PRIMARY KEY (app_id, owner, id),
    FOREIGN KEY (app_id, rule_version) REFERENCES automation_rule_sets(app_id, version)
);

CREATE INDEX IF NOT EXISTS automation_rule_runs_version
ON automation_rule_runs(app_id, rule_version);

CREATE TABLE IF NOT EXISTS automation_rule_proposals (
    app_id TEXT NOT NULL,
    owner TEXT NOT NULL,
    id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    action_key TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    proposal TEXT NOT NULL,
    dismissed_at TEXT,
    PRIMARY KEY (app_id, owner, id),
    FOREIGN KEY (app_id, owner, run_id) REFERENCES automation_rule_runs(app_id, owner, id)
);

CREATE INDEX IF NOT EXISTS automation_rule_proposals_run
ON automation_rule_proposals(app_id, owner, run_id);

CREATE INDEX IF NOT EXISTS automation_rule_proposals_action
ON automation_rule_proposals(app_id, owner, action_key, observed_at DESC);

CREATE INDEX IF NOT EXISTS automation_rule_proposals_recent
ON automation_rule_proposals(app_id, owner, observed_at DESC, id);


CREATE TABLE IF NOT EXISTS automation_rule_schedules (
    app_id TEXT PRIMARY KEY REFERENCES apps(id),
    owner TEXT NOT NULL,
    owner_version INTEGER NOT NULL,
    app_version INTEGER NOT NULL,
    version INTEGER NOT NULL,
    definition TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    next_due TEXT NOT NULL,
    expires TEXT NOT NULL,
    run_count INTEGER NOT NULL,
    max_runs INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','OFF','EXPIRED','EXHAUSTED','BLOCKED')),
    receipt_id TEXT,
    stopped_reason TEXT
);

CREATE INDEX IF NOT EXISTS automation_rule_schedules_due
ON automation_rule_schedules(status, next_due);

