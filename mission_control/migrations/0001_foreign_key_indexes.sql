-- 0001 foreign key indexes
-- Every foreign-key child column added after the original schema lacked a
-- leading index. SQLite can use these indexes for FK checks and app-scoped
-- history reads instead of scanning the whole table.
CREATE INDEX IF NOT EXISTS agent_grants_app ON agent_grants(app_id);
CREATE INDEX IF NOT EXISTS agent_handoffs_source_grant ON agent_handoffs(source_grant_id);
CREATE INDEX IF NOT EXISTS agent_handoffs_claimed_grant ON agent_handoffs(claimed_grant_id);
CREATE INDEX IF NOT EXISTS agent_review_requests_grant ON agent_review_requests(grant_id);
CREATE INDEX IF NOT EXISTS approvals_app ON approvals(app_id);
CREATE INDEX IF NOT EXISTS attribution_failures_source ON attribution_failures(app_id,source_id);
CREATE INDEX IF NOT EXISTS attribution_reads_source ON attribution_reads(app_id,source_id);
CREATE INDEX IF NOT EXISTS attribution_receipts_source ON attribution_receipts(app_id,source_id);
CREATE INDEX IF NOT EXISTS attribution_receipts_map ON attribution_receipts(app_id,map_id,map_version);
CREATE INDEX IF NOT EXISTS audit_app ON audit(app_id);
CREATE INDEX IF NOT EXISTS automation_executions_policy ON automation_executions(policy_id);
CREATE INDEX IF NOT EXISTS automation_executions_grant ON automation_executions(grant_id);
CREATE INDEX IF NOT EXISTS automation_job_scopes_execution ON automation_job_scopes(execution_id);
CREATE INDEX IF NOT EXISTS automation_policies_app ON automation_policies(app_id);
CREATE INDEX IF NOT EXISTS automation_stop_receipts_app ON automation_stop_receipts(app_id);
CREATE INDEX IF NOT EXISTS experiment_tracking_runs_job ON experiment_tracking_runs(job_id);
CREATE INDEX IF NOT EXISTS experiment_tracking_runs_experiment ON experiment_tracking_runs(app_id,experiment_id);
CREATE INDEX IF NOT EXISTS experiment_tracking_runs_source ON experiment_tracking_runs(app_id,source_id);
CREATE INDEX IF NOT EXISTS hypit_attempts_job ON hypit_attempts(job_id);
CREATE INDEX IF NOT EXISTS hypit_renders_job ON hypit_renders(job_id);
CREATE INDEX IF NOT EXISTS ios_studio_jobs_project ON ios_studio_jobs(app_id,project_id,revision);
CREATE INDEX IF NOT EXISTS onesignal_recoveries_effect ON onesignal_recoveries(effect_id);
CREATE INDEX IF NOT EXISTS onesignal_recoveries_app ON onesignal_recoveries(app_id);
CREATE INDEX IF NOT EXISTS payment_receipts_source ON payment_receipts(app_id,source_id);
CREATE INDEX IF NOT EXISTS provider_action_events_action ON provider_action_events(action_id);
CREATE INDEX IF NOT EXISTS provider_actions_app ON provider_actions(app_id);
CREATE INDEX IF NOT EXISTS sequence_jobs_app ON sequence_jobs(app_id);
CREATE INDEX IF NOT EXISTS social_flows_app ON social_flows(app_id);
CREATE INDEX IF NOT EXISTS storekit_failures_source ON storekit_failures(app_id,source_id);
CREATE INDEX IF NOT EXISTS storekit_receipts_source ON storekit_receipts(app_id,source_id);
CREATE INDEX IF NOT EXISTS studio_source_heads_version ON studio_source_heads(app_id,project_id,version);
CREATE INDEX IF NOT EXISTS verified_reviews_app ON verified_reviews(app_id);
CREATE INDEX IF NOT EXISTS video_edit_renders_job ON video_edit_renders(job_id);
CREATE INDEX IF NOT EXISTS video_project_heads_revision ON video_project_heads(app_id,id,revision);
CREATE INDEX IF NOT EXISTS workflow_events_job ON workflow_events(job_id);
