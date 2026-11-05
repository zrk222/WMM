# Spec: private-client-reads
Status: approved implementation increment; hosted public release incomplete

## MUST - Functional core
### Description
Deliver actual authenticated read-only HTTP dashboard access to separately registered client workspaces. Reuse existing Service and Store. Preserve the existing desktop listener and all mutation authority. This is the first functional private read boundary toward hosted teams, not the final generic-login or public hosted product.

### Requirements (EARS)
- The system shall return dashboard reads for active OWNER, OPERATOR, REVIEWER and VIEWER client memberships through `assigned_reads`, binding server-provisioned opaque sessions to issuer, subject and current client and member epochs.
- The system shall return only app ID, declared name and version plus app-scoped job-status counts from the registered existing Service through `projection`, with 0 raw app fields, records, job inputs/results, credentials, paths, exports or provider calls.
- If a caller selects another tenant, client, app or filesystem path, the system shall return no unassigned data through `client_isolation`, including when 2 registered stores contain the same app ID.
- If a session, membership or client expires, is revoked or changes epoch, the system shall reject its old authority through `revocation` with 0 seconds of grace; reactivation shall not restore old sessions.
- When a dashboard is collected, the system shall recheck current authority and append a hash-bound local authorization receipt before returning bytes through `final_check`; a revocation committed before that final transaction shall prevent success.
- The system shall retain session and membership state across Python server restart through `durability`, storing only SHA256 token hashes and no plaintext session tokens in the control database or receipts.
- The system shall admit only exact loopback Host, fixed GET dashboard routes, one strict bearer header and bounded identifiers through `http_boundary`, rejecting unsupported methods, local API paths, query strings, encoded separators, ambiguous headers and forwarding identity claims.
- The system shall return isolated concurrent results through `concurrency`, using immutable per-client Service instances and 0 request-time mutation of a shared Service reference.
- If a registry entry is missing, aliases another client database, points through a symlink/junction or leaves its configured private root, the system shall reject startup or access through `registry`; the HTTP request shall perform 0 database creations, migrations or path selections.
- The system shall preserve existing local desktop, owner/agent authority and workers through `local_compatibility`, adding no public listener, worker, domain write, credential migration or domain-owner impersonation.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: assigned_reads
 Given active memberships for all4roles and a trusted provisioned session
 When `assigned_reads` executes a real HTTP dashboard request
 Then only that client's declared app summary is returned
Scenario: projection
 Given raw secret sentinel fields and job inputs/results
 When `projection` serializes the actual Service summary
 Then only the whitelist and integer job-state counts appear
Scenario: client_isolation
 Given2stores with the same app ID and distinct sentinel names
 When `client_isolation` requests another unassigned client or path
 Then no other client's bytes appear
Scenario: revocation
 Given an issued session and current role
 When `revocation` changes or reactivates membership or client epoch
 Then the old session fails immediately
Scenario: final_check
 Given collection paused before response finalization
 When `final_check` observes a committed revocation or receipt persistence failure
 Then no200response or app data is returned
Scenario: durability
 Given an issued session stored only as a hash
 When `durability` reopens the control repository and server
 Then valid authority persists and expired or revoked authority stays rejected
Scenario: http_boundary
 Given real HTTP clients with malformed routes headers or methods
 When `http_boundary` receives ambiguous or unsupported input
 Then no local desktop route or domain mutation is dispatched
Scenario: concurrency
 Given2simultaneous authorized clients
 When `concurrency` reads identical app IDs repeatedly
 Then each response and receipt remains in its registered client
Scenario: registry
 Given escaping aliased missing or replaced store files
 When `registry` resolves a configured handle
 Then invalid bindings fail without initializing a caller-selected Store
Scenario: local_compatibility
 Given existing local authority and desktop tests
 When `local_compatibility` runs the unchanged runtime contract
 Then original guards and local startup remain intact
```

## SHOULD - Concrete design
Trusted administrator provisioning is an internal Python interface only, with no HTTP session-mint or membership-management endpoint. Server-owned random32byte sessions are read-only capabilities, valid15minutes idle and at most8hours absolute. They contain no role/client facts supplied by a browser; issuance snapshots active membership and client epochs. Repository changes atomically invalidate old snapshots. Production generic human sign-in is not supplied by this increment. A later reviewed identity adapter must establish immutable issuer/subject before using trusted issuance; no homemade HMAC broker or verified-claims HTTP bypass is added.

Use a dedicated SQLite control repository, separate from client databases. Only server-created immutable registry handles select pre-existing Service/Store instances. Root and resolved file containment, duplicate canonical paths/inodes, link components and control/client collisions are rejected before serving; revalidate file identity per read. Initial server binds only127.0.0.1 with no CLI/public deployment option. Bearer authorization over private loopback is explicit; production HTTPS, secure cookies, generic sign-in, protected hosted credentials and writes remain required later.

Read route GET /v1/tenants/{tenant}/clients/{client}/apps/{app}/dashboard has no query or encoded characters. Empty bodies only; reject duplicate Host/Authorization/Origin, unsupported forwarded identity headers and extra cookies. Match exact Host, optional Origin to the configured loopback origin. Unknown/unassigned client/app is404 after authentication, invalid session401, malformed400, unsupported method405, unavailable control/registry503. Responses are no-store, JSON, nosniff, max16KiB. No CORS or reuse of growth_session.

The final control transaction is the read authorization linearization point: revocation before commit denies, a read authorized before revocation may arrive later. Receipt ALLOWED means authorized response prepared, not confirmed browser delivery. Never hold the control write lock during network send. Role names do not grant existing domain OWNER/MAKER/CHECKER capabilities. No public-host, full R08/R09 completion, live-account or business-outcome claim follows from synthetic acceptance.

## Exact increment contract
Projection schema private-client-dashboard.v1 contains tenant_id, client_id, app:{id,name,version}, jobs:{queued,running,blocked,failed,succeeded,cancelled,unknown,interrupted,other}, mode PRIVATE_AUTHENTICATED_READ, effects_enabled false. All counts are nonnegative integers; unrecognized saved states increment other. No domain authority follows from any control role. GET header count is at most32 and total header text at most8KiB; route length at most512characters. Requests close their connection after a bounded response.

Filesystem administrators and Python startup code are trusted. This increment detects missing/replaced/rebound files before and after collection; it does not sandbox a privileged administrator who can swap files and restore them between checks. Deployment requires private root ownership by the service identity; no remote route can modify files or registrations. The final authority transaction may permit already-authorized bytes to arrive after a later revocation.

Dashboard collection opens existing database through sqlite3 URI mode=ro, never Store(path), initialize, ordinary db.connection or db.session during HTTP requests. A disappeared database must fail without recreation; WAL state is read using SQLite normal read-only semantics, not immutable mode.

## Authorized parameters
Production SQLite and socket timeout = 5 seconds. Test HTTP/future timeout = 10 seconds. Trusted issuance max_age default = 28800 seconds, with test max_age = 1000 seconds exercising absolute expiry. Barrier test max_workers = 1; concurrent client test max_workers = 4.
timeout = 5
timeout = 10
max_age = 28800
max_age = 1000
max_workers = 1
max_workers = 4
