# Team-session security review

Status: **LOCAL-ONLY / REMOTE ACCESS BLOCKED**

This note records what the team-session and owner-review primitives do, what they do not do, and the conditions for enabling remote team access. It is a review gate, not an authorization to expose the server.

## Current boundary

- The server binds only to `127.0.0.1`; `Server` rejects any other bind address.
- There is **no HTTP route** for team-session create, verify, list or revoke. The primitive is currently a local library surface, not a remotely reachable endpoint.
- Team session credentials are returned once and stored only as SHA-256 hashes.
- `open_session` requires an active app membership; `verify` rechecks the current active membership and returns the current role/version.
- Revocation is owner-only, exact-identity, version-bound and effective on the next verification.
- Browser routes require exact `Host`, same-origin writes and a CSRF token; there is no bearer-token shortcut for owner actions.

## Required before remote access

All of the following must be reviewed together and pass before any non-loopback listener, tunnel or hosted team endpoint is enabled:

1. **Session verification:** TLS termination, cookie/credential transport, fixation, rotation, logout and replay behavior.
2. **Current role/membership:** every request re-derives the active role and version; revoked membership invalidates live sessions.
3. **HTTPS:** no remote session or credential over plain HTTP; certificate handling is separate from provider TLS.
4. **Revocation:** owner revocation, member removal and role downgrade take effect within a bounded interval; tests cover concurrent requests.
5. **Independent security review:** a reviewer other than the author reviews the combined remote boundary before deployment.
6. **Tenant isolation:** a separate design for hosted multi-user access. The current local store is not a tenant boundary.

## Owner-only review risk

The current policy allows the owner to review security-sensitive changes without a second human reviewer. This is accepted for a solo local preview, but it reduces independent assurance. Before remote team access, materially expanding paid execution, or commercial service delivery, require an independent security review and record its scope and findings.

## Residual risks

- A stolen local browser session can act as the signed-in owner until the session ends.
- A local process running as the same OS user is outside this boundary.
- The local server is not an OS sandbox.
- Team invitations are one-time and role-bounded, but email/login identity proof depends on the identity provider and the owner choosing the right login.

See [THREAT-MODEL.md](THREAT-MODEL.md), [REVIEW-POLICY.md](REVIEW-POLICY.md) and [SECURITY.md](../SECURITY.md).
