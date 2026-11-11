# Spec: goal-readiness
Status: draft

## MUST - Functional core
### Description
Expose the existing read-only selected-workflow inventory through the protected owner HTTP control. No provider request, inference, grant, policy or work is created. For a selected recently verified Facebook destination in a publication workflow, the owner check also reports whether the required protected fields are available on this device.

### Requirements (EARS)
- The system shall return the original readiness inventory and matching digest with an additive observation envelope through `read_inventory`.
- The system shall reject unauthenticated, non-owner, stale identity, invalid CSRF and foreign-origin requests through `owner_boundary`.
- The system shall reject extra selection fields, foreign profiles or accounts and outdated app versions through `exact_selection`.
- The system shall return blockers for missing profiles, inference tests older than 24 hours, accounts expiring at or before observation time and unimplemented workflows without issuing authority through `blocked_inventory`.
- The system shall reflect current credential and owner revisions in its digest without returning private fields or changing durable data through `read_only`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: read_inventory
  Given a synthetic authenticated owner and current tested profile
  When `read_inventory` requests selected local evidence readiness over loopback HTTP
  Then the original inventory digest matches and authority remains unissued
Scenario: owner_boundary
  Given anonymous, non-owner and invalid protected request variants
  When `owner_boundary` requests readiness
  Then requests are denied before an inventory is returned
Scenario: exact_selection
  Given extra authority fields and foreign or outdated selected resources
  When `exact_selection` requests readiness
  Then the closed existing selection validators reject the request
Scenario: blocked_inventory
  Given missing, stale, expired and unimplemented requirements
  When `blocked_inventory` requests readiness
  Then every selected blocker stays visible without activation
Scenario: read_only
  Given private synthetic profile/account fields and a changed profile revision
  When `read_only` repeats readiness inspection
  Then the digest reflects the revision and database contents are unchanged by inspection
```

## SHOULD - Technical
- Reuse post_agent_grants fresh session identity and Readiness.report membership/manifest checks.
- Envelope status is success or warning, with summary, next_actions, artifacts and authority_issued false. The additive credential_repairs map names only selected Facebook account IDs and closed repair states. A missing field asks for reconnect; an unavailable store asks for protected storage to be unlocked or checked. This observation cannot authorize provider work or change the saved inventory digest.
- Preserve inventory, inventory_sha256 and observed_at returned by Readiness.report without recomputing its contents.
- HTTP authentication is tested with a synthetic GitHub adapter; no live provider acceptance is claimed.
