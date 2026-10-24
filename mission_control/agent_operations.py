"""Agent-neutral discovery of actual local operations and missing authority controls."""
from .common import digest
from .marketing_agent_manifest import operating_manifest
from .agent_feedback import TOOLS
from .operation_catalog import catalog


def discovery(app):
    """Project only public app scope and policy; discovery never grants execution."""
    policy = operating_manifest(app)
    base = "/api/apps/" + app["id"]
    tools = policy["supported_resolution_tools"]
    missing_feedback = sorted(set(tools) - set(TOOLS))
    value = {"schema": "growth.agent-operations.v1", "app_id": app["id"],
        "manifest_version": app["version"], "app_hash": digest(app["data"]), "local_catalog": catalog(),
        "policy_sha256": digest(policy), "transport": "LOOPBACK_HTTP_JSON",
        "protocol_clients": "Any authorized local client implementing this versioned HTTP/JSON contract",
        "bootstrap": {"method": "GET", "path": "/api/bootstrap",
                      "session": "Retain the returned session cookie; send the current csrf value in X-CSRF-Token and the loopback origin for writes. A session is not proof of human approval."},
        "reads": [{"method": "GET", "path": base, "purpose": "Inspect current app-owned workspace, jobs, evidence and resolution options"},
                  {"method": "GET", "path": base + "/measurement", "purpose": "Read current app-owned event reports"},
                  {"method": "GET", "path": base + "/export", "purpose": "Download the private app snapshot only to an authorized local destination"}],
        "supported_resolution_tools": list(tools),
        "resolution_execution": {"method": "POST", "path": base + "/resolutions/approve",
            "request_fields": ["issue_id", "option_id", "source_hash", "target_url", "request_key"],
            "request_source": "Use exact current issue/option parameters returned by the workspace; do not invent IDs or source hashes",
            "approval_boundary": "EXISTING_LOCAL_CONFIRMATION_ONLY",
            "independent_human_approval_enforced": False,
            "agent_autonomous_use": "NOT_AUTHORIZED_BY_DISCOVERY"},
        "checkpoints": [
            {"action": "provider_promotional_text", "state": "EXISTING_MAKER_CHECKER_PATH",
             "requirement": "Fresh authenticated maker and distinct checker, exact target/baseline/hash/expiry and explicit final send; discovery grants no authority"},
            {"action": "catalog_local_writes", "state": "SCOPED_GRANTS_AND_INDEPENDENT_REVIEW_IMPLEMENTED",
             "requirement": "Use an owner-issued grant. Owner-selected review operations require prepare, a separate fresh distinct checker approval, and exact durable resume. Inspect the catalog; discovery grants no authority."},
            {"action": "spend_publish_paywall_sensitive_access_destructive", "state": "HUMAN_CHECKPOINT_REQUIRED",
             "requirement": "No agent self-approval. Unsupported effect adapters remain manual; do not bypass existing approval or access controls"}],
        "native_agent_adapters": {"purpose": "Bounded text drafts", "tool_execution_enabled": False},
        "coverage": {"complete_autonomous_operation": False, "feedback_missing_tools": missing_feedback,
            "remaining": ["Complete domain operation catalog and request/result schemas", "Provider-specific authorized effect adapters", "Full workflow conformance through two independent clients"]},
        "execution_authority": False, "external_writes": False, "spend_minor": 0}
    return dict(value, contract_sha256=digest(value))
