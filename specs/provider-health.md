# Spec: provider-health

Status: draft

## MUST - Functional core
### Description
Project saved app-owned provider state into one read-only health view. Each
supported provider shows its current observed state, explicit permission basis,
scope, expiry when stored, a bounded failure code and one exact recovery path.
Login, key presence or publishing access never implies analytics permission or
verified delivery.

### Requirements (EARS)
- The system shall project `provider_health` from saved store connections, analytics sources, social publishing accounts and Google Play login flows through `provider_health`.
- The system shall return one row per supported provider with `provider`, `kind`, observed `state`, `login_state`, `permission_state`, saved scope, stored `expires_at`, bounded `failure`, `next_action` and `recovery_route`.
- The system shall keep analytics permission distinct: a protected store key or untested social login reports `ANALYTICS_READ_UNVERIFIED` or `PUBLISHING_ONLY_NOT_ANALYTICS`, never a successful analytics read.
- The system shall retain only a bounded uppercase failure code and shall replace any raw provider message with `READ_FAILED`.
- The system shall choose one highest-priority `recovery` entry, preferring reconnect, expired, disconnected and permission-required states over pending or healthy states.
- The system shall exclude credentials, credential references, API keys, tokens, raw provider messages and private configuration from the projection.
- The system shall expose the projection in the workspace and render it on the Connections page with the explicit boundary that login is not analytics permission.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: provider_health_separation
  Given a protected store connection, an analytics source and a social publishing login
  When `provider_health` is projected
  Then each keeps its own observed state and permission basis
  And no login or key presence is reported as analytics permission
Scenario: provider_health_recovery
  Given reconnect, permission and pending states
  When the recovery is chosen
  Then one highest-priority exact next action is returned
  And a healthy or absent provider is not invented
Scenario: provider_health_privacy
  Given saved credential references, tokens and raw provider errors
  When the projection is rendered
  Then none of them appear
  And failures remain bounded codes
```
