# Spec: automation-readiness
Status: draft

## MUST - Functional core
### Description
Implement the credential and workflow inventory required by complete automation.
Read current app-owned facts without creating grants, resolving secrets, invoking
tools or treating a configured connection as executable standing authority.
This prerequisite does not omit any parent workflow or implement activation.

### Requirements (EARS)
- The system shall return an explicit workflow map covering the fixed operation catalog and reject unmapped catalog changes through `closed_inventory`.
- The system shall return app-owned inference verification as TESTED_FRESH only when its status is TESTED and its successful test is between zero and 24 hours old through `inference_readiness`.
- The system shall return selected social account identity, destination, scopes, expiry and read verification state while identifying publication as unimplemented through `social_readiness`.
- The system shall return an owner-only hash-bound inventory of the selected workflows and credential revisions without issuing authority, reading secret values or performing external work through `owner_inventory`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: closed_inventory
  Given the current fixed operation catalog and a new unmapped operation
  When `closed_inventory` validates each catalog
  Then the current catalog is fully mapped and the changed catalog is rejected
Scenario: inference_readiness
  Given configured, freshly tested, stale, future-dated and disconnected profiles
  When `inference_readiness` reads their selected app facts
  Then only the freshly tested profile is reported TESTED_FRESH
Scenario: social_readiness
  Given current and expired read-tested social accounts
  When `social_readiness` reads selected account facts
  Then their subject, destination and read state are explicit and no publishing capability is reported
Scenario: owner_inventory
  Given an independently authenticated owner and a foreign principal
  When `owner_inventory` reads a selected scope
  Then only the owner receives exact current bindings and no authority or secret is created
```

## SHOULD - Technical
- Use the existing SQLite connection and membership check in one read transaction.
  Exact app, owner-role, operation-map, profile and account revisions participate
  in the inventory hash. The report is NOT an activation or execution receipt.
- Require a closed selection with one agent identity, current manifest version,
  selected workflow IDs, optional inference profile ID and selected account IDs.
  Reject duplicates, unknown workflow IDs, malformed identifiers and foreign
  accounts/profiles. Do not load all accounts or silently choose a fallback.
- Include all parent families: local evidence, local experiment and pipeline
  preparation, Hypit captions, native rendering, viral discovery, video authoring
  and editing, complete analytics, social publication, release delivery and paid
  effects. Explicit blockers retain incomplete family requirements.
- Return public provider/model/task and account scope/verification fields only.
  Protected references, tool paths, raw key/token material and renewal leases are
  excluded. Readiness does not prove current protected-secret availability,
  installed-tool identity, media runtime, pricing, quotas or live provider state;
  mark these as requiring activation/dispatch validation.
- Limits: one through 11 selected workflows and zero through 20 account IDs.
  A successful test exactly 24 hours old is accepted; older or future timestamps
  are not fresh. Unknown account expiry is not treated as non-expiring access.
- Synthetic tests use the fixed timestamp 2026-10-24T12:00:00+00:00 as input data.
  Production inspection uses the current UTC clock, not this test timestamp.

## Authorized parameters
MAX_WORKFLOWS = 11
MAX_ACCOUNTS = 20
FRESH_HOURS = 24
