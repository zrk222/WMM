# ADR 0001: Team tier architecture

- **Status:** Proposed — authorizes no code by itself.
- **Date:** 2026-11-08
- **Owners:** Product/security (needs a second human reviewer; see P4)

## Context

WMM today is a local-first, single-operator product:

- The server binds loopback and validates `Host`/`Origin` as `127.0.0.1:PORT`.
- Data is one SQLite file per installation; credentials live in the OS vault.
- Authority is scoped to one owner per app, plus `MAKER`/`CHECKER` roles that
  already exist in `operator_roles`.
- Every effect is server-enforced and audited; exports exclude authority.

The buyer request is a team tier: a shared dashboard, multiple users, roles and
approvals. The current transport and storage model cannot be exposed as-is:
"keep the desktop server private on loopback" is an explicit product boundary,
and the desktop macOS credential adapter is unsupported.

Relevant existing pieces we can reuse instead of rebuilding:

- `operator_roles` (OWNER/MAKER/CHECKER, versioned, audited), maker/checker
  review flows and distinct-reviewer checks.
- App-scoped grants, expiry/consent receipts, standing agreements and the
  server-side enforcement boundary.
- Snapshot validation and authority exclusions.
- Weekly portfolio projection and the unified activity timeline.

## Options

### A. Hosted multi-tenant SaaS (recommended long term)

One cloud control plane, strong tenant isolation, OIDC/SSO, billing. Best buyer
experience and the only realistic path to self-serve signup. Largest security
surface: tenant isolation, credential handling in the cloud, data residency and
a new incident-response burden.

### B. Owner-hosted shared team server (recommended first release)

Each team runs one WMM instance on a host they control, reached over HTTPS.
Same codebase, new authenticated transport and invitations. Faster to ship, keeps
provider credentials on the team's host, and avoids multi-tenant isolation risk
in v1. Buyers must run a host; this is the same trade-off as self-hosted tools.

### C. Keep local per-user (status quo)

No shared dashboard. Lowest risk and cost, but does not satisfy the P1 request.

## Decision

Ship **Option B** as the first team tier, with an explicit path to Option A.

Reasons:

1. It preserves WMM's strongest property: provider credentials stay on the
   team's host and never enter a shared cloud database.
2. Most isolation work becomes "one deployment per team", not "many tenants in
   one database".
3. The existing role, approval and audit model carries over with invitations and
   remote authentication layered on top.
4. It can be validated with one design-partner team before taking on multi-tenant
   security obligations.

Option A remains the target once demand, retention and a security review justify
it. Nothing in this ADR authorizes a hosted service, billing or public signup.

## Phase 1 scope (owner-hosted team server)

Must have:

- **Transport:** HTTPS only (no loopback-only assumption for team mode), strict
  `Host`/`Origin`, secure cookies, CSRF, HSTS, no public signup.
- **Identity:** OIDC or GitHub OAuth sign-in; owner invitations; no password
  storage; sessions revocable; MFA delegated to the identity provider.
- **Roles:** existing OWNER/MAKER/CHECKER, plus explicit invitation and
  revocation; a checker must be a different human from the maker.
- **Shared dashboard:** weekly review, activity timeline and provider health
  across all team apps, with per-app access checks.
- **Authority:** grants, budgets, expiry and AGENT origin remain server-enforced
  exactly as audited; team mode adds no new widening path.
- **Audit:** append-only actor/time/action records; no secrets in logs or exports.
- **Credentials:** stay in the host's OS vault or a supported secret store per
  team; never in the shared database, exports or agent context.
- **Recovery:** backup/restore of the team database; explicit key custody.
- **Deployment:** documented container/systemd install, upgrade and uninstall;
  no terminal-only setup for ordinary members.

Explicitly out of scope for Phase 1:

- Self-serve signup, billing, per-seat pricing, public cloud hosting.
- Multi-tenant data sharing, cross-team analytics.
- Mobile/native team clients.
- macOS credential support.
- Any change to default zero spend.

## Security model

- Authentication is delegated; WMM never stores passwords.
- Authorization is re-derived from the team database on every request and every
  protected operation, as the P0 audit requires.
- A team member sees only apps and evidence their role allows; app access is
  explicit, not implied by team membership.
- Maker/checker separation and exact approvals remain per app.
- Agent permission slips remain app-scoped, expiry-bound and revocable.
- Provider effects keep their own exact approvals; team membership never grants
  campaign or spend authority.

## Data model changes (Phase 1)

Add, without rewriting current tables:

- `teams` and `team_members` (identity principal, role, status, version).
- `app_memberships` (app, principal, role, version) — existing
  `operator_roles` can remain the per-app authority table.
- `invitations` (email or provider identity, role, token hash, expiry, state).
- `sessions` (hashed session id, principal, expiry, revocation).
- `audit_actors` (server-derived actor identity for existing audit rows).

Do not copy credentials, grants or verified evidence between apps or teams.
Snapshots continue to exclude authority.

## Migration path

1. Keep the desktop single-operator mode unchanged.
2. Add a team mode that runs the same schema with remote auth and HTTPS.
3. Migrate an existing local workspace by copying the database and app records,
   never the OS vault. Re-authenticate each provider on the team host.
4. Reissue grants and approvals explicitly; do not resurrect agent or campaign
   authority from a copied workspace.

## First code slice (after approval)

1. Threat model and deployment guide (HTTPS, identity provider, key custody).
2. Team/session/invitation schema plus migrations.
3. Remote authentication and authorization middleware with tests that prove
   loopback assumptions cannot be reused.
4. Team weekly/dashboard read paths with per-app access checks.
5. Owner-hosted package and upgrade path.

## Open questions for the owner

1. Which identity provider first: GitHub OAuth (already present) or generic OIDC?
2. Is an owner-hosted host acceptable for the first buyers, or is hosted required
   before any team sale?
3. Who is the second human reviewer for the security-sensitive work?
4. Which single design-partner team will validate Phase 1?

## Consequences

- Positive: fastest safe path to a shared dashboard; credentials stay private;
  reuses roles/approvals; avoids multi-tenant isolation risk in v1.
- Negative: buyers must run a host; two deployment modes to test; identity and
  session code is new; hosted SaaS remains future work.
- Not doing this: no team tier. Choosing Option A instead requires a larger
  security and operations program before the first buyer.
