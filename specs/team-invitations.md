# Spec: team-invitations

Status: draft

## MUST - Functional core
### Description
Add the first team-tier data layer without changing the local-first product: an
app owner can invite a named GitHub login to the existing `MAKER` or `CHECKER`
role with a one-time, expiring credential. The invitee accepts only with their
own verified identity. This is not public signup, not a hosted tenant and not an
OWNER grant.

### Requirements (EARS)
- The system shall let an active app OWNER issue one invitation with exactly `login`, `role` and `expires` through `invite_issue`.
- The system shall accept only a bounded GitHub login, `MAKER` or `CHECKER`, and an expiry between one hour and seven days.
- The system shall return the invitation credential once and store only its SHA-256; invitation listing and snapshots never expose it.
- When an invitation is accepted, the system shall require a verified identity whose login matches, a pending unexpired invitation, and no existing OWNER role for that principal.
- When accepted, the system shall write the invited MAKER or CHECKER role through the existing versioned app-role path and mark the invitation accepted atomically.
- The system shall reject expired, revoked, already accepted, wrong-login, cross-app or self-owner acceptance without writing.
- The system shall let the OWNER revoke a pending invitation by exact identity and version.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: invite_issue
  Given an app owner
  When the owner invites a GitHub login as MAKER or CHECKER
  Then the credential is returned once and stored only as a hash
Scenario: invite_accept
  Given a pending invitation for a GitHub login
  When that verified identity accepts it
  Then the app role is written once
  And the invitation cannot be reused
Scenario: invite_denial
  Given expired, revoked, wrong-login or OWNER-assignment attempts
  When acceptance or issuance is attempted
  Then no role changes
Scenario: invite_scope
  Given invitations for one app
  When another app or non-owner reads them
  Then access is denied
```
