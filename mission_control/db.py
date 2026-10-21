"""Independent SQLite persistence with foreign keys and transactional writes."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS play_flows(id TEXT PRIMARY KEY,app_id TEXT NOT NULL REFERENCES apps(id),manifest_version INTEGER NOT NULL,connection_id TEXT,connection_version INTEGER NOT NULL,state_hash TEXT NOT NULL UNIQUE,secret_ref TEXT NOT NULL,config TEXT NOT NULL,status TEXT NOT NULL,expires REAL NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,result TEXT);
CREATE INDEX IF NOT EXISTS play_flow_app ON play_flows(app_id,created);
CREATE TABLE IF NOT EXISTS play_retirements(app_id TEXT NOT NULL REFERENCES apps(id),reference TEXT NOT NULL,eligible REAL NOT NULL,PRIMARY KEY(app_id,reference));
CREATE TABLE IF NOT EXISTS social_configs(app_id TEXT NOT NULL REFERENCES apps(id),provider TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,secret_ref TEXT,status TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,provider));
CREATE TABLE IF NOT EXISTS social_flows(id TEXT PRIMARY KEY,app_id TEXT NOT NULL REFERENCES apps(id),provider TEXT NOT NULL,config_version INTEGER NOT NULL,state_hash TEXT NOT NULL UNIQUE,secret_ref TEXT,data TEXT NOT NULL,status TEXT NOT NULL,result TEXT,expires REAL NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS social_connections(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,provider TEXT NOT NULL,config_version INTEGER NOT NULL,version INTEGER NOT NULL,subject_id TEXT NOT NULL,data TEXT NOT NULL,secret_ref TEXT,status TEXT NOT NULL,expires REAL,refresh_expires REAL,renewed_at REAL NOT NULL,lease TEXT,lease_until REAL NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS social_retirements(app_id TEXT NOT NULL REFERENCES apps(id),provider TEXT NOT NULL,reference TEXT NOT NULL,eligible REAL NOT NULL,PRIMARY KEY(app_id,provider,reference));
CREATE TABLE IF NOT EXISTS agent_connections(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,status TEXT NOT NULL,last_test TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS agent_routes(app_id TEXT PRIMARY KEY REFERENCES apps(id),version INTEGER NOT NULL,data TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_retirements(app_id TEXT NOT NULL REFERENCES apps(id),reference TEXT NOT NULL,eligible REAL NOT NULL,PRIMARY KEY(app_id,reference));
CREATE TABLE IF NOT EXISTS inspection_config(app_id TEXT PRIMARY KEY REFERENCES apps(id),version INTEGER NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inspection_archives(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS inspection_runs(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','SUCCEEDED','INCOMPLETE','BLOCKED','CANCELLED','INTERRUPTED')),result TEXT,error TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,request_hash TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS pmf_research(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('study','snapshot','receipt')),data TEXT NOT NULL,hash TEXT NOT NULL,imported INTEGER NOT NULL CHECK(imported IN (0,1)),created TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS followup_policy(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,version INTEGER NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS followup_subject(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,version INTEGER NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS followup_task(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,version INTEGER NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS followup_handoff(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,version INTEGER NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS attribution_sources(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,version INTEGER NOT NULL,status TEXT NOT NULL,imported INTEGER NOT NULL,scope_key TEXT NOT NULL,read_grant INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS attribution_maps(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS attribution_receipts(app_id TEXT NOT NULL,id TEXT NOT NULL,source_id TEXT NOT NULL,map_id TEXT,map_version INTEGER,identity TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id),FOREIGN KEY(app_id,source_id) REFERENCES attribution_sources(app_id,id),FOREIGN KEY(app_id,map_id,map_version) REFERENCES attribution_maps(app_id,id,version));
CREATE INDEX IF NOT EXISTS attribution_identity ON attribution_receipts(app_id,identity);
CREATE TABLE IF NOT EXISTS attribution_failures(app_id TEXT NOT NULL,id TEXT NOT NULL,source_id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id),FOREIGN KEY(app_id,source_id) REFERENCES attribution_sources(app_id,id));
CREATE TABLE IF NOT EXISTS attribution_reads(app_id TEXT NOT NULL,id TEXT NOT NULL,source_id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,status TEXT NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id),FOREIGN KEY(app_id,source_id) REFERENCES attribution_sources(app_id,id));
CREATE TABLE IF NOT EXISTS production_profiles(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS production_requirements(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS storekit_sources(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,version INTEGER NOT NULL,status TEXT NOT NULL,imported INTEGER NOT NULL,scope_key TEXT NOT NULL,read_grant INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS storekit_receipts(app_id TEXT NOT NULL,id TEXT NOT NULL,source_id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,status TEXT NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id),FOREIGN KEY(app_id,source_id) REFERENCES storekit_sources(app_id,id));
CREATE TABLE IF NOT EXISTS storekit_failures(app_id TEXT NOT NULL,id TEXT NOT NULL,source_id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id),FOREIGN KEY(app_id,source_id) REFERENCES storekit_sources(app_id,id));
CREATE TABLE IF NOT EXISTS insight_sources(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,provider TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,scope_key TEXT NOT NULL,credential_ref TEXT NOT NULL,version INTEGER NOT NULL,status TEXT NOT NULL,lease REAL NOT NULL,next_due REAL NOT NULL,last_error TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,provider),UNIQUE(app_id,id));
CREATE TABLE IF NOT EXISTS insight_reports(app_id TEXT NOT NULL,id TEXT NOT NULL,source_id TEXT NOT NULL,provider TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id),FOREIGN KEY(app_id,source_id) REFERENCES insight_sources(app_id,id));
CREATE TABLE IF NOT EXISTS insight_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,scope_key TEXT NOT NULL,attempted REAL NOT NULL);
CREATE TABLE IF NOT EXISTS insight_cleanup(app_id TEXT NOT NULL,source_id TEXT NOT NULL,credential_ref TEXT NOT NULL,PRIMARY KEY(app_id,source_id,credential_ref));
CREATE TABLE IF NOT EXISTS payment_sources(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,version INTEGER NOT NULL,status TEXT NOT NULL,imported INTEGER NOT NULL,credential_ref TEXT NOT NULL,secret_hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS payment_receipts(app_id TEXT NOT NULL REFERENCES apps(id),event_id TEXT NOT NULL,source_id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,status TEXT NOT NULL,imported INTEGER NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,event_id),FOREIGN KEY(app_id,source_id) REFERENCES payment_sources(app_id,id));
CREATE TABLE IF NOT EXISTS payment_attempts(app_id TEXT NOT NULL,event_id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,event_id,version),FOREIGN KEY(app_id,event_id) REFERENCES payment_receipts(app_id,event_id));
CREATE TABLE IF NOT EXISTS payment_effects(app_id TEXT NOT NULL REFERENCES apps(id),object_id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,object_id));
CREATE TABLE IF NOT EXISTS creative_outcome_links(app_id TEXT NOT NULL REFERENCES apps(id),experiment_id TEXT NOT NULL,arm TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,experiment_id,arm,version));
CREATE TABLE IF NOT EXISTS learning_programs(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,state TEXT NOT NULL,version INTEGER NOT NULL,preparer TEXT NOT NULL,restored INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS learning_events(app_id TEXT NOT NULL REFERENCES apps(id),learning_id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,learning_id,version));
CREATE TABLE IF NOT EXISTS learning_experiment_roles(app_id TEXT NOT NULL REFERENCES apps(id),experiment_id TEXT NOT NULL,role TEXT NOT NULL,learning_id TEXT NOT NULL,PRIMARY KEY(app_id,experiment_id));
CREATE TABLE IF NOT EXISTS learning_active(app_id TEXT PRIMARY KEY REFERENCES apps(id),learning_id TEXT);
CREATE TABLE IF NOT EXISTS learning_brief_uses(app_id TEXT NOT NULL REFERENCES apps(id),brief_id TEXT NOT NULL,learning_id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(app_id,brief_id));
CREATE TABLE IF NOT EXISTS apps(id TEXT PRIMARY KEY, data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operator_roles(app_id TEXT NOT NULL REFERENCES apps(id),principal TEXT NOT NULL,login TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL,version INTEGER NOT NULL,updated TEXT NOT NULL,changed_by TEXT NOT NULL,PRIMARY KEY(app_id,principal));
CREATE TABLE IF NOT EXISTS verified_reviews(id TEXT PRIMARY KEY,app_id TEXT NOT NULL REFERENCES apps(id),packet TEXT NOT NULL,hash TEXT NOT NULL,preparer TEXT NOT NULL,checker TEXT,checker_role_version INTEGER,status TEXT NOT NULL,expires TEXT NOT NULL,created TEXT NOT NULL,reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS provider_actions(id TEXT PRIMARY KEY,app_id TEXT NOT NULL REFERENCES apps(id),target_key TEXT NOT NULL,packet TEXT NOT NULL,hash TEXT NOT NULL,preparer TEXT NOT NULL,checker TEXT,checker_role_version INTEGER,status TEXT NOT NULL,dispatches INTEGER NOT NULL DEFAULT 0,lease REAL NOT NULL DEFAULT 0,owner TEXT,expires TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS provider_action_target ON provider_actions(target_key,status);
CREATE TABLE IF NOT EXISTS provider_action_events(id INTEGER PRIMARY KEY AUTOINCREMENT,action_id TEXT NOT NULL REFERENCES provider_actions(id),data TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), kind TEXT NOT NULL, title TEXT NOT NULL, data TEXT NOT NULL, source TEXT NOT NULL, provenance TEXT NOT NULL, hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS record_app_kind ON records(app_id,kind);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), action TEXT NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, lease REAL NOT NULL DEFAULT 0, result TEXT, created TEXT NOT NULL, updated TEXT NOT NULL, request_key TEXT NOT NULL, UNIQUE(app_id,request_key));
CREATE TABLE IF NOT EXISTS campaign_sequences(id TEXT PRIMARY KEY,app_id TEXT NOT NULL REFERENCES apps(id),plan TEXT NOT NULL,plan_hash TEXT NOT NULL,original_request TEXT NOT NULL,request_key TEXT NOT NULL,state TEXT NOT NULL,result TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,UNIQUE(app_id,request_key));
CREATE TABLE IF NOT EXISTS sequence_jobs(run_id TEXT NOT NULL REFERENCES campaign_sequences(id),app_id TEXT NOT NULL REFERENCES apps(id),job_id TEXT NOT NULL REFERENCES jobs(id),owned INTEGER NOT NULL CHECK(owned IN (0,1)),data_hash TEXT NOT NULL,PRIMARY KEY(run_id,job_id));
CREATE INDEX IF NOT EXISTS sequence_job_lookup ON sequence_jobs(job_id,owned);
CREATE UNIQUE INDEX IF NOT EXISTS sequence_job_owner ON sequence_jobs(job_id) WHERE owned=1;
CREATE INDEX IF NOT EXISTS sequence_ready ON campaign_sequences(state,updated);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT NOT NULL REFERENCES apps(id), action TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), packet TEXT NOT NULL, hash TEXT NOT NULL, preparer TEXT NOT NULL, checker TEXT, status TEXT NOT NULL, expires TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS growth_cohorts(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS growth_events(app_id TEXT NOT NULL, provider TEXT NOT NULL, external_id TEXT NOT NULL, cohort_id TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, imported TEXT NOT NULL, PRIMARY KEY(app_id,provider,external_id), FOREIGN KEY(app_id,cohort_id) REFERENCES growth_cohorts(app_id,id));
CREATE INDEX IF NOT EXISTS growth_event_cohort ON growth_events(app_id,cohort_id);
CREATE TABLE IF NOT EXISTS experiments(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, state TEXT NOT NULL, version INTEGER NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS experiment_tracking_runs(id TEXT PRIMARY KEY,app_id TEXT NOT NULL,experiment_id TEXT NOT NULL,source_id TEXT NOT NULL,plan TEXT NOT NULL,hash TEXT NOT NULL,original_request TEXT NOT NULL,request_key TEXT NOT NULL,status TEXT NOT NULL,result TEXT,result_hash TEXT,job_id TEXT NOT NULL REFERENCES jobs(id),expires TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,UNIQUE(app_id,request_key),FOREIGN KEY(app_id,experiment_id) REFERENCES experiments(app_id,id),FOREIGN KEY(app_id,source_id) REFERENCES insight_sources(app_id,id));
CREATE INDEX IF NOT EXISTS experiment_tracking_history ON experiment_tracking_runs(app_id,created);
CREATE TABLE IF NOT EXISTS experiment_assessments(app_id TEXT NOT NULL, experiment_id TEXT NOT NULL, hash TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(app_id,experiment_id,version), FOREIGN KEY(app_id,experiment_id) REFERENCES experiments(app_id,id));
CREATE TABLE IF NOT EXISTS experiment_actions(id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT NOT NULL, experiment_id TEXT NOT NULL, hash TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(app_id,experiment_id,hash), FOREIGN KEY(app_id,experiment_id) REFERENCES experiments(app_id,id));
CREATE TABLE IF NOT EXISTS experiment_schedules(app_id TEXT NOT NULL, experiment_id TEXT NOT NULL, enabled INTEGER NOT NULL, interval_hours INTEGER NOT NULL, version INTEGER NOT NULL, next_due TEXT NOT NULL, last_job TEXT, reconciled_job TEXT, failures INTEGER NOT NULL, status TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(app_id,experiment_id), FOREIGN KEY(app_id,experiment_id) REFERENCES experiments(app_id,id));
CREATE TABLE IF NOT EXISTS creative_references(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, identity TEXT NOT NULL, PRIMARY KEY(app_id,id), UNIQUE(app_id,identity));
CREATE TABLE IF NOT EXISTS creative_captures(app_id TEXT NOT NULL, reference_id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,reference_id,version), FOREIGN KEY(app_id,reference_id) REFERENCES creative_references(app_id,id));
CREATE TABLE IF NOT EXISTS creative_analyses(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS creative_briefs(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS creative_rank_policies(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS creative_relevance(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS creative_rank_reports(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS acquisition_intents(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS acquisition_panels(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS acquisition_observations(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS acquisition_reports(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id,version));
CREATE TABLE IF NOT EXISTS creative_renders(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, job_id TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,id), UNIQUE(app_id,job_id));
CREATE TABLE IF NOT EXISTS aeo_checks(app_id TEXT NOT NULL REFERENCES apps(id), id TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL, origin TEXT NOT NULL CHECK(origin IN ('LOCAL_OBSERVATION','IMPORTED_ASSERTION')), PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS setup_proposals(app_id TEXT NOT NULL REFERENCES apps(id),id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('PENDING','NEEDS_RESOLUTION','APPLIED')),result TEXT,created TEXT NOT NULL,expires TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(app_id,id));
"""


@contextmanager
def connection(path):
    """Open a transactional SQLite connection with foreign-key enforcement."""
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path):
    """Initialize only the independent local database and its indexes."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
