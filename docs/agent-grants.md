# Scoped local agent credentials

An app owner can delegate selected fixed local operations to an agent. A grant freezes the app revision, content hash, owner-role revision, operation allowlist, expiry and call ceiling. It identifies that delegated agent; it is separate from an AI provider key and from an independently authenticated human reviewer.

Grant management uses the existing local browser session, CSRF protection and freshly reverified GitHub owner identity. A caller-supplied owner name or grant bearer credential cannot manage grants. No automatic first-owner setup or GitHub sign-in is performed by an agent adapter.

Owner HTTP operations, using the selected app ID:

| POST address | Exact JSON body | Result |
| --- | --- | --- |
| `/api/apps/{app_id}/agent-grants/issue` | `agent_id`, `manifest_version`, `operations`, `expires`, `max_calls` | Public grant metadata and a random `token`, returned once |
| `/api/apps/{app_id}/agent-grants/list` | `{}` | Public state, usage, versions and scopes; no token/hash |
| `/api/apps/{app_id}/agent-grants/revoke` | `id`, `version` | New revoked revision; future admissions denied |

`agent_id` uses lowercase letters, digits and hyphens. Select operation names from the shared catalog. `expires` is an ISO timestamp within the next 24 hours; `max_calls` is a whole number from 1 through 10000. App changes or owner-role revision changes invalidate the grant. Loss of the one-time token requires revoking it and issuing a new grant; it cannot be recovered from listing, snapshots or workspace exports.

The owner can deliver the credential through the authorized host's process environment under **WMM_AGENT_GRANT**. Do not put its value in command arguments, source files, logs, reports or shared transcripts. Neither adapter reads a provider key as a WMM grant. Choose your host's protected credential entry mechanism; this packet does not install or configure an external host.

From the repository root, with that environment supplied:

```powershell
python -m mission_control.agent_cli call --origin http://127.0.0.1:57599 --use-grant
python -m mission_control.agent_mcp --origin http://127.0.0.1:57599 --use-grant
```

CLI reads the existing JSON envelope from stdin. MCP exposes its existing tool arguments and returns the same `structuredContent.data` business result. Add `--use-grant` to the MCP host's process arguments. Without the flag, the existing trusted-local client behavior remains. With it, a missing, malformed, expired, exhausted or unauthorized credential fails; it never falls back to an ordinary browser session.

The exact bearer gateway is `POST /api/agent-operations/call` with the existing closed operation envelope, one `Authorization: Bearer ...` header, exact loopback `Host`, matching `Origin`, JSON content type and one bounded content length. It creates no cookie or CSRF session. It admits a call transactionally, then dispatches the existing authoritative WMM service. Grants cannot call their own management endpoints, human approvals, identity login, credentials, publication, spending, provider mutation, arbitrary URLs or shell commands.

Every admitted attempt consumes one call, including a later business-validation failure. Concurrent requests cannot exceed the call ceiling. Revocation blocks new admissions; an operation already admitted may finish. Cancellation or a lost response does not prove rollback. Inspect saved history before retrying an uncertain write. Grant metadata and call-admission audit events stay in the local operational database; bearer plaintext is not persisted or exported.

These credentials restrict the delegated gateway. Existing trusted-local browser/service interfaces remain available to the workstation user. This is not an OS sandbox against arbitrary code with that user's full workstation permissions. The owner issuance/management API is functional; dedicated human-facing grant-management screens remain required UI work. Complete domain schemas, all operation coverage, independently authenticated human checkpoint dispatch/resume and real-provider acceptance remain separate required integration. A grant does not approve publication, payments, live paywalls or spending.
