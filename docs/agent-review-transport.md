# Exact agent requests and independent human review

An owner can issue a grant with an optional `review_operations` array containing a subset of its granted local write operations. An ordinary call to one of those operations is denied. The agent prepares the exact input, a different authenticated checker reviews it, and the agent resumes that saved request once. Approval does not allow editing the input or using a replacement grant. Model-provider credentials never establish checker identity.

The service and HTTP/client workflow are implemented. A dedicated human review screen and grant-management screen remain required UI work. Use these APIs only through an authorized local integration; this document does not activate real identities or issue production credentials.

Agents use a host-supplied **WMM_AGENT_GRANT** process environment value and the explicit `--use-grant` flag. No token value belongs in arguments, logs, source or reports. CLI commands read strict JSON on stdin from the repository root:

```powershell
python -m mission_control.agent_cli review-prepare --origin http://127.0.0.1:57599 --use-grant
python -m mission_control.agent_cli review-status --origin http://127.0.0.1:57599 --use-grant
python -m mission_control.agent_cli review-resume --origin http://127.0.0.1:57599 --use-grant
```

| Action | Exact stdin JSON fields | Result |
| --- | --- | --- |
| prepare | `id`, `envelope` | Frozen full operation envelope and `WAITING_REVIEW` checkpoint |
| status | `app_id`, `id` | Checkpoint, exact saved input and any durable result receipt |
| resume | `app_id`, `id`, `revision`, `packet_hash` | Execution receipt for the saved approved input |

The envelope uses the existing fixed catalog's `app_id`, `operation`, `input` and optional `resource_id`. Read the current approved checkpoint revision and its `hash` before resume; the required `packet_hash` is the checkpoint hash, not the input hash. Extra fields, replacement input, actor names, approval flags and wrong grant/app identities are rejected.

The optional MCP adapter launched with `--use-grant` advertises **19 tools**: the original catalog and fifteen operations plus `wmm_review_prepare`, `wmm_review_status` and `wmm_review_resume`. Their arguments are the same JSON bodies in the table. Without a grant, the adapter advertises the original sixteen tools and rejects review actions without browser-session fallback. There is no agent approval tool. Results retain `structuredContent.data`.

Bearer HTTP routes are exactly `POST /api/agent-operations/reviews/prepare`, `/status` and `/resume`. They require one scoped Authorization bearer header, exact loopback Host and matching Origin, JSON content type and unambiguous bounded framing. They create no browser cookie or CSRF session. Preparation and execution each reserve a grant attempt; status can inspect the receipt after its call quota is exhausted, while the grant remains current.

Human actions use the existing CSRF browser session and freshly reverified GitHub identity at `POST /api/apps/{app_id}/agent-reviews/{action}`:

| Action | Exact body |
| --- | --- |
| list | `{}` or `{"offset":0}`; returns total, at most 100 metadata items and next_offset |
| inspect | `id`; returns the exact proposed input, checkpoint and receipt |
| approve | `id`, `revision`, `packet_hash`; requires current distinct checker |
| cancel | `id`, `revision`; requires maker, checker or owner |
| reconcile | `id`, `revision`, `outcome`, `evidence_hash`; requires a distinct current checker and known outcome with a SHA256 evidence reference |

All human routes require current app membership. List responses omit the large operation input; inspect each exact request before approving. Follow `next_offset` to read older requests. Recheck the queue while new requests arrive. A caller-supplied login, principal or bearer credential grants no human review authority. The preparer's delegated owner cannot approve their own request.

Expired or revoked grants, changed app or role versions, stale hashes/revisions and repeated resumes are rejected. Cancellation before claim prevents execution. A crash, lost response or cancellation during execution requires inspecting the stored receipt and current domain history; do not automatically retry. Unknown outcomes and reconciliation remain explicit. Approval and grants are excluded from snapshot authority. This controls the delegated gateway, not arbitrary code with the workstation user's full permissions.

Full-domain coverage, final human UI/accessibility/report acceptance, genuine provider/human acceptance, expanded BYOK/OAuth/local transports and broad CF release assurance remain INCOMPLETE. No publication, spending, external messages, payment/paywall change or provider action is authorized by these local review operations.
