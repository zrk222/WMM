# Spec: agent-grants
Status: draft

## MUST - Functional core
### Description
Add owner-issued bearer grants for the current fixed local operation catalog. Reuse authenticated GitHub owner roles and authoritative domain services. Both CLI and MCP can opt into a grant without command-line secrets or browser-session bootstrap. Complete domain coverage and independent human checkpoint dispatch remain mandatory follow-up integration, not supplied by a grant.

### Requirements (EARS)
- The system shall issue a random bearer credential once under a freshly authenticated app owner and store only its SHA256 hash with exact app version, app hash, owner role version, operation allowlist, expiry and call ceiling through `grant_issue`.
- The system shall reject unknown tokens, revoked grants, expired grants with lifetime at most 24 hours, changed owner roles, changed app scope, unauthorized operations and exhausted owner-selected call counts before service dispatch through `grant_admission`.
- The system shall reserve each admitted call atomically and expose public grant state and optimistic-version revocation to the freshly authenticated owner through `grant_lifecycle`.
- The system shall execute admitted calls only through the existing fixed catalog and authoritative services while rejecting human approval, credentials, arbitrary routes and provider effects through `grant_dispatch`.
- The system shall return the same business results through optional grant-aware CLI and official SDK MCP transports without cookie bootstrap, token arguments, token logging or fallback to ordinary session authority through `grant_clients`.
- The system shall exclude grants and credentials from snapshots and ordinary workspace data, and reject body-supplied human identities at owner endpoints through `grant_privacy`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: grant_issue
  Given an authenticated owner in an isolated workspace
  When `grant_issue` is exercised
  Then the credential is returned once and only its hash is persisted
Scenario: grant_admission
  Given an issued scoped credential
  When `grant_admission` is exercised
  Then invalid or unavailable authority is rejected before execution
Scenario: grant_lifecycle
  Given concurrent callers and an exact grant revision
  When `grant_lifecycle` is exercised
  Then call admission respects the ceiling and revocation prevents new admission
Scenario: grant_dispatch
  Given a valid grant for one local operation
  When `grant_dispatch` is exercised
  Then the authoritative service returns its result and unsupported effects remain unavailable
Scenario: grant_clients
  Given real CLI and official SDK MCP subprocesses
  When `grant_clients` is exercised
  Then both operate the same scoped saved history without browser-session creation or fallback
Scenario: grant_privacy
  Given exported workspace data and a caller requesting owner access
  When `grant_privacy` is exercised
  Then neither exported data nor caller-supplied identity can grant authority
```

## SHOULD - Technical
- Limits: maximum grant lifetime 24 hours; max_calls is an integer from 1 through 10000. A random token uses secrets.token_urlsafe(32) with prefix wmmg_. Existing transport MAX_BYTES = 16777216 and TIMEOUT_SECONDS = 15 remain. Test subprocess timeout = 30; async fixture timeout = 45.
- Explicit client flag --use-grant reads WMM_AGENT_GRANT from the process environment; absent or malformed values fail before network. A bearer token identifies the delegated agent grant, not an independent human checker.
- Only exact loopback Host and Origin are accepted at the bearer gateway. It creates no cookie session and accepts strict finite duplicate-free JSON. Unknown grant authority returns denial and never falls back to browser-session authorization.
- Admission consumes quota even if subsequent business validation fails. Revocation blocks future admissions; an already admitted operation may finish and must not be blindly retried. No inference token/cost measurement or workload sandbox is claimed.
- Existing trusted-local UI/service endpoints remain available. This gateway is a scoped interface for cooperative agent hosts, not an OS sandbox against code with the workstation's full permissions. No remote listener, real identity credential, publication, spend or provider effect is activated by this packet.

## Authorized parameters
Synthetic quota cases include valid and invalid boundary fixtures:
max_calls = 10
max_calls = 1
max_calls = 0
max_calls = 10001
max_workers = 8
timeout = 15
timeout = 30
timeout = 45
