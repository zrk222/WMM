# Spec: team-sessions

Status: draft

## MUST - Functional core
### Description
Issue durable app-scoped sessions after GitHub identity verification. This is the
session layer beneath the team tier: no passwords are stored, only a hash of a
one-time session credential, and every session is expiring and revocable. Hosted
HTTPS transport, member UI and a full OIDC provider remain separate work.

### Requirements (EARS)
- The system shall verify a GitHub token through the fixed `github_read('/user')` reader and open a session for the returned principal and login through `login`.
- The system shall also open a session for an already verified identity through `open_session`.
- The system shall bind each session to one app, a principal, a login, a provider, a creation time and an expiry between 1 and 720 hours.
- The system shall return the session credential once and store only its SHA-256.
- The system shall deny unknown, expired or revoked session credentials through `verify`.
- The system shall let an app OWNER list sessions and revoke one by exact identity and version; non-owners are denied.
- The system shall not store passwords, raw GitHub tokens, session plaintext or hosted-tenant data.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: session_login
  Given a GitHub token verified as one person
  When the session opens
  Then the credential is returned once and only its hash is stored
  And verify resolves that person and app
Scenario: session_expiry_revocation
  Given an expired or revoked session
  When verify or owner listing runs
  Then access is denied or marked revoked
Scenario: session_scope
  Given sessions for one app
  When a non-owner or another app requests them
  Then access is denied
  And no password or raw token exists in storage
```
