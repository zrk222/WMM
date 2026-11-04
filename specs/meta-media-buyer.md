# Spec: meta-media-buyer

## MUST - Functional core
### Description
Provide an app-bound Meta media-buying specialist through the existing WMM
manifest and operations.read interface. Use ECC action/observation/recovery
guidance and reviewed public REA research. Keep the general agent's response
compact; load the specialist explicitly without adding a tool or permission.
Current campaign effect adapters remain authoritative.

### Requirements (EARS)
- The system shall return a compact Meta specialist index in the general operating manifest through `meta_index`, naming its existing read operation and exact profile input.
- When profile meta_media_buyer is selected, the system shall return an app-bound hashed specialist contract through `meta_profile`, covering research, measurement, creative tests, finite owner scope, execution, monitoring, reconciliation and owner reporting.
- The system shall reject unknown, malformed and mixed profile selectors through `meta_selector`, preserving the empty-input general read and app/grant boundaries across HTTP, CLI and MCP.
- The system shall return evidence requirements and explicit decisions for observation, preparation, authorized execution, pause, reconciliation and missing implementation through `meta_decisions`, granting 0 additional operations and 0 automatic paid units.
- The system shall distinguish current Meta engagement capabilities from unimplemented campaign objectives and campaign-setting mutations through `meta_capabilities`, making no provider calls through unimplemented adapters and never treating a plan or vendor promise as execution.
- The system shall return source provenance and observation, attribution-window, cost, uncertainty and next-action fields for owner reporting through `meta_evidence`, retaining unknown measurements as null rather than predicted outcomes.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: meta_index
  Given the current general app operating manifest
  When a personal agent reads its specialist index
  Then it can request the Meta profile through operations.read without a new tool or grant
Scenario: meta_profile
  Given an authorized app-scoped read
  When the exact Meta profile is requested
  Then its app context, source hash, rules, decisions and report fields are returned consistently
Scenario: meta_selector
  Given general, valid, invalid and cross-app requests
  When the supported read-only adapters resolve the profile input
  Then empty input retains the general response while only the exact supported selector and current app authority succeed
Scenario: meta_decisions
  Given a media-buying plan with missing data, authority or an uncertain mutation
  When the specialist contract is read
  Then it requires the relevant evidence and safe next action without self-approval, fabricated metrics or automatic mutation replay
Scenario: meta_capabilities
  Given the current fixed operation catalog and campaign connector
  When specialist capabilities are returned
  Then every named operation exists and Meta engagement execution is distinguished from unsupported app campaigns and budget edits
Scenario: meta_evidence
  Given public reference patterns and partial app observations
  When the owner report requirements are read
  Then vendor claims, forecasts, provider delivery, measured app outcomes and missing evidence remain distinct
```

## Authorized parameters
META_PROFILE_VERSION = 1
META_DEFAULT_SPEND_MINOR = 0

## Non-goals
No new provider adapter, campaign objective, grant, external access or spending
authority. No attribution, keyword-volume, ROAS, growth or savings claim from
public ad counters. A specialist contract is not a successful live campaign.
