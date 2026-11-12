"""Generated row types for the assembled core schema.

Regenerate with ``python tools/generate_schema_types.py`` after any schema
change. The core scope is ``db.py`` plus the host-installed ``onesignal_setup``
schema; domain modules that install their own tables remain separate.
"""
from typing import TypedDict


class AcquisitionIntentsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class AcquisitionObservationsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class AcquisitionPanelsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class AcquisitionReportsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class AeoChecksRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    created: str
    origin: str


class AgentCheckpointsRow(TypedDict):
    app_id: str
    id: str
    data: str
    revision: int


class AgentConnectionsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    status: str
    last_test: str | None
    created: str
    updated: str


class AgentGrantReviewPolicyRow(TypedDict):
    grant_id: str
    operations: str


class AgentGrantsRow(TypedDict):
    id: str
    app_id: str
    agent_id: str
    owner: str
    owner_version: int
    app_version: int
    app_hash: str
    operations: str
    token_hash: str
    expires: str
    max_calls: int
    used: int
    status: str
    version: int
    created: str
    updated: str


class AgentHandoffsRow(TypedDict):
    id: str
    app_id: str
    source_grant_id: str | None
    recipient: str
    payload: str
    payload_hash: str
    created: str
    expires: str
    status: str
    claimed_grant_id: str | None
    claimed_at: str | None
    version: int


class AgentRetirementsRow(TypedDict):
    app_id: str
    reference: str
    eligible: float


class AgentReviewRequestsRow(TypedDict):
    app_id: str
    id: str
    grant_id: str
    envelope: str
    input_hash: str
    result: str | None


class AgentRoutesRow(TypedDict):
    app_id: str
    version: int
    data: str
    updated: str


class AppleMetricPartitionsRow(TypedDict):
    app_id: str
    store_app_id: str
    connection_id: str
    connection_version: int
    report_id: str
    report_family: str
    granularity: str
    event_date: str
    processing_date: str
    fingerprint: str
    source_hash: str
    data: str
    byte_count: int
    ingested_at: str


class AppleMetricsSchedulesRow(TypedDict):
    app_id: str
    id: str
    connection_id: str
    connection_version: int
    connection_hash: str
    app_version: int
    report_id: str
    interval_hours: int
    enabled: int
    version: int
    next_due: float
    last_due: float | None
    last_job: str | None
    reconciled_job: str | None
    failures: int
    status: str
    last_success: str | None
    last_error: str | None
    updated: str


class ApprovalsRow(TypedDict):
    id: str
    app_id: str
    packet: str
    hash: str
    preparer: str
    checker: str | None
    status: str
    expires: str
    created: str


class AppsRow(TypedDict):
    id: str
    data: str
    version: int
    updated: str


class AttributionFailuresRow(TypedDict):
    app_id: str
    id: str
    source_id: str
    data: str
    hash: str
    imported: int
    created: str


class AttributionMapsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    imported: int
    created: str


class AttributionReadsRow(TypedDict):
    app_id: str
    id: str
    source_id: str
    data: str
    hash: str
    status: str
    imported: int
    created: str


class AttributionReceiptsRow(TypedDict):
    app_id: str
    id: str
    source_id: str
    map_id: str | None
    map_version: int | None
    identity: str
    data: str
    hash: str
    imported: int
    created: str


class AttributionSourcesRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    version: int
    status: str
    imported: int
    scope_key: str
    read_grant: int
    created: str


class AuditRow(TypedDict):
    id: int
    app_id: str
    action: str
    detail: str
    created: str


class AuthorityExpiryConsentsRow(TypedDict):
    app_id: str
    kind: str
    authority_id: str
    revision: int
    base_hash: str
    previous_hash: str
    old_expiry: str
    new_expiry: str
    owner: str
    owner_version: int
    preview_hash: str
    request_id: str
    confirmed: str
    receipt_hash: str
    stable_hash: str


class AutomationExecutionAuthorityRow(TypedDict):
    execution_id: str
    permission_expires_at: str
    policy_revision: int
    policy_hash: str
    grant_revision: int
    grant_hash: str
    record_hash: str


class AutomationExecutionsRow(TypedDict):
    id: str
    policy_id: str
    policy_version: int
    grant_id: str
    operation: str
    input_hash: str
    status: str
    write_commits: int
    result_hash: str | None
    created: str
    updated: str


class AutomationJobScopesRow(TypedDict):
    job_id: str
    execution_id: str
    request_hash: str


class AutomationPoliciesRow(TypedDict):
    id: str
    app_id: str
    grant_id: str
    owner: str
    version: int
    status: str
    proposal: str
    summary: str
    summary_hash: str
    created: str
    updated: str


class AutomationRuleSetsRow(TypedDict):
    app_id: str
    version: int
    document: str
    hash: str
    created: str
    created_by: str


class AutomationStopReceiptsRow(TypedDict):
    policy_id: str
    app_id: str
    owner: str
    owner_version: int
    prior_version: int
    owned_jobs_stopped: int
    created: str


class CampaignSequencesRow(TypedDict):
    id: str
    app_id: str
    plan: str
    plan_hash: str
    original_request: str
    request_key: str
    state: str
    result: str
    created: str
    updated: str


class CloudConnectionsRow(TypedDict):
    app_id: str
    endpoint: str
    credential_ref: str
    status: str
    last_test: str | None
    last_error: str | None
    version: int
    created: str
    updated: str


class CreativeAnalysesRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class CreativeBatchVariantsRow(TypedDict):
    app_id: str
    batch_id: str
    ordinal: int
    request_key: str
    request: str
    request_hash: str
    job_id: str | None
    inspection: str | None
    inspection_hash: str | None
    native_state: str
    native_packet_hash: str | None


class CreativeBatchesRow(TypedDict):
    app_id: str
    id: str
    request_key: str
    request_hash: str
    plan: str
    plan_hash: str
    state: str
    reserved_frames: int
    created: str
    updated: str


class CreativeBriefsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class CreativeCapturesRow(TypedDict):
    app_id: str
    reference_id: str
    version: int
    data: str
    hash: str
    created: str


class CreativeOutcomeLinksRow(TypedDict):
    app_id: str
    experiment_id: str
    arm: str
    version: int
    data: str
    hash: str
    created: str


class CreativeRankPoliciesRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class CreativeRankReportsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class CreativeReferencesRow(TypedDict):
    app_id: str
    id: str
    identity: str


class CreativeRelevanceRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class CreativeRendersRow(TypedDict):
    app_id: str
    id: str
    job_id: str
    data: str
    hash: str
    created: str


class CreativeTasteReviewsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class CustomerWorkflowsRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    created: str
    imported: int


class DiscoveryDocumentsRow(TypedDict):
    app_id: str
    id: str
    version: int
    kind: str
    data: str
    hash: str
    created: str


class DriveConnectionsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    secret_ref: str | None
    status: str
    expires: float | None
    created: str
    updated: str


class DriveFlowsRow(TypedDict):
    id: str
    app_id: str
    manifest_version: int
    connection_id: str | None
    connection_version: int
    state_hash: str
    secret_ref: str
    data: str
    status: str
    expires: float
    created: str
    updated: str
    result: str | None


class DriveRetirementsRow(TypedDict):
    app_id: str
    reference: str
    eligible: float


class ExperimentActionsRow(TypedDict):
    id: int
    app_id: str
    experiment_id: str
    hash: str
    data: str
    created: str


class ExperimentAssessmentsRow(TypedDict):
    app_id: str
    experiment_id: str
    hash: str
    data: str
    created: str
    version: int


class ExperimentScheduleLimitsRow(TypedDict):
    app_id: str
    experiment_id: str
    schedule_version: int
    owner: str
    owner_version: int
    app_version: int
    experiment_hash: str
    expires: str
    max_observations: int
    reserved: int


class ExperimentSchedulesRow(TypedDict):
    app_id: str
    experiment_id: str
    enabled: int
    interval_hours: int
    version: int
    next_due: str
    last_job: str | None
    reconciled_job: str | None
    failures: int
    status: str
    updated: str


class ExperimentTrackingRunsRow(TypedDict):
    id: str
    app_id: str
    experiment_id: str
    source_id: str
    plan: str
    hash: str
    original_request: str
    request_key: str
    status: str
    result: str | None
    result_hash: str | None
    job_id: str
    expires: str
    created: str
    updated: str


class ExperimentsRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    state: str
    version: int
    created: str
    updated: str


class FollowupHandoffRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    version: int
    imported: int
    created: str
    updated: str


class FollowupPolicyRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    version: int
    imported: int
    created: str
    updated: str


class FollowupSubjectRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    version: int
    imported: int
    created: str
    updated: str


class FollowupTaskRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    version: int
    imported: int
    created: str
    updated: str


class FunnelObservationsRow(TypedDict):
    app_id: str
    funnel_id: str
    source_ref: str
    event_id: str
    data: str
    hash: str
    created: str


class GrowthCohortsRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    created: str


class GrowthEventsRow(TypedDict):
    app_id: str
    provider: str
    external_id: str
    cohort_id: str
    data: str
    hash: str
    imported: str


class GrowthFunnelsRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    created: str


class GrowthReviewEntriesRow(TypedDict):
    app_id: str
    id: str
    kind: str
    data: str
    hash: str
    context: str
    created: str
    imported: int


class HypitAttemptsRow(TypedDict):
    app_id: str
    job_id: str
    attempt: int
    data: str
    hash: str
    status: str
    created: str
    updated: str


class HypitRendersRow(TypedDict):
    app_id: str
    id: str
    job_id: str
    data: str
    hash: str
    created: str


class InsightCleanupRow(TypedDict):
    app_id: str
    source_id: str
    credential_ref: str


class InsightReportsRow(TypedDict):
    app_id: str
    id: str
    source_id: str
    provider: str
    data: str
    hash: str
    created: str


class InsightRequestsRow(TypedDict):
    id: int
    scope_key: str
    attempted: float


class InsightSourcesRow(TypedDict):
    app_id: str
    id: str
    provider: str
    data: str
    hash: str
    scope_key: str
    credential_ref: str
    version: int
    status: str
    lease: float
    next_due: float
    last_error: str | None
    created: str
    updated: str


class InspectionArchivesRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    created: str


class InspectionConfigRow(TypedDict):
    app_id: str
    version: int
    data: str
    hash: str
    updated: str


class InspectionRunsRow(TypedDict):
    app_id: str
    id: str
    data: str
    status: str
    result: str | None
    error: str | None
    created: str
    updated: str
    request_hash: str


class InstallAttributionBatchesRow(TypedDict):
    app_id: str
    id: str
    campaign_token: str
    source: str
    data: str
    hash: str
    created: str


class InstallAttributionRowsRow(TypedDict):
    app_id: str
    batch_id: str
    campaign_token: str
    source: str
    install_id: str
    state: str
    occurred_at: str
    created: str


class InstallImportPreviewsRow(TypedDict):
    app_id: str
    owner: str
    id: str
    role_version: int
    app_version: int
    request_hash: str
    expires: str


class InstrumentationReceiptsRow(TypedDict):
    app_id: str
    id: str
    experiment_id: str
    proposal_hash: str
    bundle_hash: str
    state: str
    previous_id: str | None
    data: str
    hash: str
    created: str


class IosAgentMediaAuthorityRow(TypedDict):
    app_id: str
    kind: str
    job_id: str
    grant_id: str
    grant_version: int
    envelope: str
    review: str | None


class IosAgentMediaStandingRow(TypedDict):
    app_id: str
    kind: str
    job_id: str
    execution_id: str
    execution_hash: str


class IosAgentTimelineJobsRow(TypedDict):
    app_id: str
    id: str
    owner: str
    request_key: str
    request_hash: str
    packet: str
    packet_hash: str
    status: str
    result: str | None
    created: str
    updated: str


class IosStudioJobsRow(TypedDict):
    app_id: str
    id: str
    project_id: str
    revision: int
    source_hash: str
    packet_hash: str
    owner: str
    request_key: str
    request_hash: str
    status: str
    result: str | None
    created: str
    updated: str


class IosStudioProjectsRow(TypedDict):
    app_id: str
    id: str
    revision: int
    manifest_version: int
    scene: str
    source_hash: str
    owner: str
    request_key: str
    request_hash: str
    created: str


class JobsRow(TypedDict):
    id: str
    app_id: str
    action: str
    data: str
    status: str
    attempts: int
    lease: float
    result: str | None
    created: str
    updated: str
    request_key: str


class LearningActiveRow(TypedDict):
    app_id: str
    learning_id: str | None


class LearningBriefUsesRow(TypedDict):
    app_id: str
    brief_id: str
    learning_id: str
    data: str
    hash: str
    created: str


class LearningEventsRow(TypedDict):
    app_id: str
    learning_id: str
    version: int
    data: str
    hash: str
    created: str


class LearningExperimentRolesRow(TypedDict):
    app_id: str
    experiment_id: str
    role: str
    learning_id: str


class LearningProgramsRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    state: str
    version: int
    preparer: str
    restored: int
    created: str
    updated: str


class ManagedMediaRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    request_key: str
    request_hash: str
    created: str


class ManagedMediaReviewsRow(TypedDict):
    app_id: str
    media_id: str
    version: int
    data: str
    hash: str
    created: str


class NativeOwnerReviewIdentityRow(TypedDict):
    app_id: str
    native_owner: str
    github_principal: str
    login: str


class NativeStoreKeyCleanupRow(TypedDict):
    app_id: str
    provider: str
    credential_ref: str


class NoticeSettingsRow(TypedDict):
    app_id: str
    enabled: int
    updated: str


class NoticesRow(TypedDict):
    app_id: str
    id: str
    kind: str
    title: str
    state: str
    created: str
    delivered_at: str | None
    outcome: str | None


class OnesignalConnectionsRow(TypedDict):
    app_id: str
    owner: str
    version: int
    kind: str
    secret_ref: str
    provider_app_id: str | None
    organization_id: str | None
    data: str
    created: str
    updated: str


class OnesignalRecoveriesRow(TypedDict):
    id: str
    app_id: str
    owner: str
    effect_id: str
    packet: str
    packet_hash: str
    secret_ref: str | None
    status: str
    result: str | None
    created: str
    updated: str


class OnesignalRetirementsRow(TypedDict):
    app_id: str
    owner: str
    reference: str
    eligible: float


class OnesignalSetupEffectsRow(TypedDict):
    id: str
    app_id: str
    owner: str
    request_key: str
    action: str
    packet: str
    packet_hash: str
    status: str
    secret_ref: str | None
    provider_app_id: str | None
    result: str | None
    created: str
    updated: str


class OperatorRolesRow(TypedDict):
    app_id: str
    principal: str
    login: str
    role: str
    status: str
    version: int
    updated: str
    changed_by: str


class PackagingDocumentsRow(TypedDict):
    app_id: str
    id: str
    version: int
    kind: str
    data: str
    hash: str
    created: str


class PaymentAttemptsRow(TypedDict):
    app_id: str
    event_id: str
    version: int
    data: str
    hash: str
    created: str


class PaymentEffectsRow(TypedDict):
    app_id: str
    object_id: str
    data: str
    hash: str
    created: str


class PaymentReceiptsRow(TypedDict):
    app_id: str
    event_id: str
    source_id: str
    data: str
    hash: str
    status: str
    imported: int
    created: str


class PaymentSourcesRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    version: int
    status: str
    imported: int
    credential_ref: str
    secret_hash: str
    created: str


class PlayFlowsRow(TypedDict):
    id: str
    app_id: str
    manifest_version: int
    connection_id: str | None
    connection_version: int
    state_hash: str
    secret_ref: str
    config: str
    status: str
    expires: float
    created: str
    updated: str
    result: str | None


class PlayRetirementsRow(TypedDict):
    app_id: str
    reference: str
    eligible: float


class PmfResearchRow(TypedDict):
    app_id: str
    id: str
    kind: str
    data: str
    hash: str
    imported: int
    created: str


class ProductionProfilesRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class ProductionRequirementsRow(TypedDict):
    app_id: str
    id: str
    version: int
    data: str
    hash: str
    created: str


class ProviderActionEventsRow(TypedDict):
    id: int
    action_id: str
    data: str
    hash: str
    created: str


class ProviderActionsRow(TypedDict):
    id: str
    app_id: str
    target_key: str
    packet: str
    hash: str
    preparer: str
    checker: str | None
    checker_role_version: int | None
    status: str
    dispatches: int
    lease: float
    owner: str | None
    expires: str
    created: str
    updated: str


class RecordsRow(TypedDict):
    id: str
    app_id: str
    kind: str
    title: str
    data: str
    source: str
    provenance: str
    hash: str
    version: int
    updated: str


class SequenceJobsRow(TypedDict):
    run_id: str
    app_id: str
    job_id: str
    owned: int
    data_hash: str


class SetupProposalsRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    state: str
    result: str | None
    created: str
    expires: str
    updated: str


class SocialConfigsRow(TypedDict):
    app_id: str
    provider: str
    version: int
    data: str
    secret_ref: str | None
    status: str
    created: str
    updated: str


class SocialConnectionsRow(TypedDict):
    app_id: str
    id: str
    provider: str
    config_version: int
    version: int
    subject_id: str
    data: str
    secret_ref: str | None
    status: str
    expires: float | None
    refresh_expires: float | None
    renewed_at: float
    lease: str | None
    lease_until: float
    created: str
    updated: str


class SocialFlowsRow(TypedDict):
    id: str
    app_id: str
    provider: str
    config_version: int
    state_hash: str
    secret_ref: str | None
    data: str
    status: str
    result: str | None
    expires: float
    created: str
    updated: str


class SocialRetirementsRow(TypedDict):
    app_id: str
    provider: str
    reference: str
    eligible: float


class StorekitFailuresRow(TypedDict):
    app_id: str
    id: str
    source_id: str
    data: str
    hash: str
    imported: int
    created: str


class StorekitReceiptsRow(TypedDict):
    app_id: str
    id: str
    source_id: str
    data: str
    hash: str
    status: str
    imported: int
    created: str


class StorekitSourcesRow(TypedDict):
    app_id: str
    id: str
    data: str
    hash: str
    version: int
    status: str
    imported: int
    scope_key: str
    read_grant: int
    created: str


class StudioEditAttemptsRow(TypedDict):
    app_id: str
    project_id: str
    id: str
    request_key: str
    data: str
    hash: str
    status: str
    result_version: int | None
    created: str
    updated: str


class StudioSessionsRow(TypedDict):
    app_id: str
    id: str
    request_key: str
    data: str
    hash: str


class StudioSourceHeadsRow(TypedDict):
    app_id: str
    project_id: str
    version: int


class StudioSourceVersionsRow(TypedDict):
    app_id: str
    project_id: str
    version: int
    data: str
    hash: str
    created: str


class TeamInvitationsRow(TypedDict):
    app_id: str
    id: str
    token_hash: str
    login: str
    role: str
    status: str
    expires: str
    created: str
    created_by: str
    created_by_login: str
    accepted_by: str | None
    accepted_at: str | None
    version: int


class TeamSessionsRow(TypedDict):
    app_id: str
    id: str
    token_hash: str
    principal: str
    login: str
    provider: str
    created: str
    expires: str
    revoked: int
    version: int


class VerifiedReviewsRow(TypedDict):
    id: str
    app_id: str
    packet: str
    hash: str
    preparer: str
    checker: str | None
    checker_role_version: int | None
    status: str
    expires: str
    created: str
    reviewed_at: str | None


class VideoEditRendersRow(TypedDict):
    app_id: str
    id: str
    job_id: str
    data: str
    hash: str
    created: str


class VideoProjectHeadsRow(TypedDict):
    app_id: str
    id: str
    revision: int
    undo: str
    redo: str


class VideoProjectRevisionsRow(TypedDict):
    app_id: str
    id: str
    revision: int
    data: str
    hash: str
    parent_revision: int
    actor: str
    action: str
    request_key: str
    request_hash: str
    created: str


class WorkflowEventsRow(TypedDict):
    id: int
    app_id: str
    job_id: str
    attempt: int
    code: str
    stage: int | None
    observed_at: str
