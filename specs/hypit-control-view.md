# Spec: hypit-control-view
Status: draft

## MUST - Functional core
### Description
Project every compiled Hypit inspector field into a shared data-only control view
with opaque session-scoped owner/field identities. Retain native source endpoints
only inside the broker. This module prepares typed parameter proposals; it neither
executes mutations nor grants authority. Full parent Studio/editing scope remains.

### Requirements (EARS)
- The system shall return every item and track-object compiled inspector field with its declared schema and presentation through opaque session-bound identities using `control_inventory`.
- The system shall return only declared public metadata without native paths, source edits, source preimages, preview HTML or unknown metadata through `control_privacy`.
- The system shall reject stale revision/hash, foreign owner/field combinations, derived read-only edits and extra proposal fields through `control_binding`.
- The system shall reject nonfinite JSON, more than 1 MiB JSON bytes and invalid primitive control proposals while returning only the upstream parameter mutation vocabulary through `control_proposal`.
- The system shall preserve list/record structures and explicitly require upstream schema validation and current authority before any execution through `control_authority`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: control_inventory
  Given multiple compiled item and track-object inspectors
  When `control_inventory` is projected
  Then every field remains available with opaque identities and declared public schemas
Scenario: control_privacy
  Given compiled snapshots with private native endpoints and source preimages
  When `control_privacy` returns its public data
  Then source endpoints and executable preview HTML are absent
Scenario: control_binding
  Given a current projected inspector
  When `control_binding` receives a foreign field, stale revision or changed hash
  Then no native mutation proposal is returned
Scenario: control_proposal
  Given a writable compiled field
  When `control_proposal` receives invalid JSON or primitive type
  Then the proposal is rejected before any upstream request
Scenario: control_authority
  Given accepted list and record proposal structures
  When `control_authority` prepares the native mutation
  Then the receipt remains a proposal and requires current upstream validation and broker approval
```

## Authorized parameters
MAX_JSON_BYTES = 1048576
MAX_FIELDS = 10000
MAX_OWNERS = 1000
MAX_DEPTH = 32

## SHOULD - Integration boundary
The current session broker must build this view only from a fresh owned compiled
snapshot and enforce authority at execution. A proposal hash is not approval.
Native IDs remain internal and never become caller-controlled source patches.
Complex list/record schema semantics, units and source serialization remain owned
by the selected upstream Companion and mutation compiler. The projector does not
pretend to replace those checks. Additional fields are discovered dynamically;
there is no caption-only inventory ceiling. No HTML rendering is performed here.
