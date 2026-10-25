# Spec: agent-review-transport
Status: draft

## MUST - Functional core
### Description
Expose the exact reviewed local operation service to scoped agents and independently authenticated human reviewers. Share finite action schemas across HTTP, CLI and optional MCP. A dedicated human review UI remains required separate work; this increment proves authenticated API and two-client operation without claiming full product acceptance.

### Requirements (EARS)
- The system shall return closed agent request schemas for prepare, status and resume with fixed gateway paths and no approve action through `review_protocol`.
- The system shall reject malformed fields, alternate paths and missing or wrong scoped bearer grants before reviewed service access through `agent_gateway`.
- The system shall require freshly verified human identity, current app membership and exact checkpoint hash/revision for human approval while rejecting body-supplied identity through `human_gateway`.
- The system shall return app-scoped exact request details and a paginated human queue of 100 requests per page without exporting credentials through `human_inspection`.
- The system shall return matching reviewed execution receipts through real CLI and official SDK MCP subprocesses with no browser-session fallback through `review_clients`.
- The system shall reject self approval, agent approval, wrong grant/app, stale requests and duplicate resume while retaining cancellation or unknown receipts through `review_recovery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: review_protocol
  Given the fixed reviewed request contract
  When `review_protocol` is exercised
  Then only closed prepare status and resume schemas are returned to agents
Scenario: agent_gateway
  Given a scoped bearer client on exact loopback
  When `agent_gateway` is exercised
  Then valid calls reach the shared service and malformed or unauthorized calls fail
Scenario: human_gateway
  Given separate owner and checker sessions
  When `human_gateway` is exercised
  Then freshly authenticated distinct checker approval is required and supplied names grant no authority
Scenario: human_inspection
  Given app-owned reviewed requests
  When `human_inspection` is exercised
  Then exact details and paginated app history are returned without grant credentials
Scenario: review_clients
  Given CLI and official SDK MCP subprocesses
  When `review_clients` is exercised
  Then preparation approval resume and readback use the same immutable request and result
Scenario: review_recovery
  Given cancelled stale or uncertain reviewed work
  When `review_recovery` is exercised
  Then no client can rearm or approve it and durable history remains inspectable
```

## SHOULD - Technical
- Agent actions require an explicit grant; no ordinary local-session fallback or human login/approval tools. MCP advertises these actions only when launched with a grant. Catalog discovery remains offline.
- Existing exact loopback Host/Origin, finite strict duplicate-free JSON, MAX_BYTES = 16777216 and TIMEOUT_SECONDS = 15 remain. No remote listener, auto retry, credential installation, provider mutation or execution capability is added.
- Human list/detail/actions use the existing CSRF session and freshly reverified GitHub identity. Approve/cancel/reconcile reuse Checkpoints role/version/state validation. Private request input is available only to app members and the exact delegated grant.
- Human queue pagination includes total and next_offset, validates integer offsets and orders by request identity. Expired/revoked agent grants cannot access requests; authorized humans can inspect and reconcile them. No token or human identity is accepted through a request body.
- Agent status/resume lookup must return the same denial for a wrong token or wrong grant whether a request ID exists or not; resolve the exact grant/request binding before reading private details.
- Full-domain coverage, human review/grant-management UI, broad CF release assurance, real human/provider acceptance and production activation remain incomplete. Tests use synthetic authenticated identity responses and isolated databases.

## Authorized parameters
PAGE_SIZE = 100
timeout = 15
timeout = 30
timeout = 45
max_calls = 100
