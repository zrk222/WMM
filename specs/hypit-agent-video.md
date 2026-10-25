# Spec: hypit-agent-video
Status: approved scope; implementation pending

## MUST - Functional core
### Description
Add a first-class Agent-made video option. The selected user agent authors Hypit compositions from approved app facts and owned media, renders locally, and returns editable sources and an actual previewable, downloadable MP4. The default profile requires no paid video-generation API. UPG-07 is additive to the existing WMM goal.

### User roles
- Owner selects an agent and approves frozen context transmission and any separately requested paid profile.
- Agent authors and revises within the approved app workspace and production profile.
- Human reviewer approves the exact video artifact before separately authorized publication.

### Requirements (EARS)
- The system shall display Agent-made video in the existing production UI with selected agent, approved inputs, local rendering, progress, revision, preview and MP4/source download through `first_class_option`.
- The system shall bind production to the selected app, current brief, approved claims, rights-cleared asset hashes, selected connection and independently approved context through `source_binding`.
- The system shall render an authored-graphics and supplied-media Hypit graph with no paid video-generation endpoint or automatic paid fallback through `local_production`.
- The system shall retain build identity, tool versions, editable source, actual output checksum and decoded media receipt while distinguishing agent cost, local compute and video API cost through `artifact_delivery`.
- The system shall reuse explicitly selected accepted outputs for variants and invalidate affected alignment when speech changes through `variant_reuse`.
- The system shall abort cancelled owned attempts, store failure diagnostics and inspect uncertain completion before retrying with at most 3 attempts per job through `recovery`.
- The system shall reject publication without independent authority and human review of exactly the output checksum being published through `publication_boundary`.
- The system shall return production preparation, status, cancellation and artifact receipts through app-scoped CLI and MCP grants and human checkpoints through `agent_operation_parity`.
- The system shall store source-linked production KPI observations and display post-publication retention, completion, shares and attributed product outcomes under exactly the declared observation window with PDF export through `outcome_reporting`.
- The system shall detect a user-installed Hypit runtime, preserve its attribution and reject unsupported hosted profiles without silently switching providers through `runtime_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: first_class_option
  Given the production page at desktop and mobile widths
  When Agent-made video is selected through `first_class_option`
  Then the user can select an agent and complete the integrated preview and download workflow
Scenario: source_binding
  Given an approved request
  When its app, facts, asset bytes or connection changes through `source_binding`
  Then execution requires a new bound request and approval
Scenario: local_production
  Given a prepared local Hypit runtime and approved agent
  When the agent authors and builds a composition through `local_production`
  Then an actual decoded MP4 is produced without a paid video-generation request
Scenario: artifact_delivery
  Given a completed local render
  When the user previews and downloads it through `artifact_delivery`
  Then media dimensions, duration and checksum match the saved receipt and editable sources remain available
Scenario: variant_reuse
  Given accepted body media and a changed opening
  When a variant is rendered through `variant_reuse`
  Then unchanged outputs are explicitly retained and changed dependencies are rebuilt
Scenario: recovery
  Given an interrupted or cancelled attempt
  When saved status is inspected before retry through `recovery`
  Then diagnostics identify the owned attempt and no duplicate completed artifact is committed
Scenario: publication_boundary
  Given a human-reviewed artifact
  When different bytes are substituted or publication authority is absent through `publication_boundary`
  Then publication is denied
Scenario: agent_operation_parity
  Given actual CLI and MCP clients with scoped grants
  When production operations are exercised through `agent_operation_parity`
  Then matching app-owned receipts are returned and cross-app access is denied
Scenario: outcome_reporting
  Given production receipts without published performance or billing telemetry
  When analytics and PDF export are opened through `outcome_reporting`
  Then observed production facts are shown and unavailable outcomes and costs remain unknown
Scenario: runtime_boundary
  Given a missing Hypit runtime or unsupported hosted profile
  When production is prepared through `runtime_boundary`
  Then its exact setup or authorization requirement is displayed without an automatic provider fallback
```

## SHOULD - Technical
- Resolve the execution boundary for agent-authored code before admitting executable components. A subprocess is not a sandbox. Do not expose arbitrary shell commands through general operations.
- Use existing source-currentness, app isolation, durable jobs, credential and human-checkpoint services. Preserve the native renderer and unrelated work.
- Define an explicit Hypit video/audio validation profile without weakening the native silent-video profile. Cover malformed media, cancellation, restart and portable restore.
- Initially support user-operated local Hypit installations; review its current license before commercial bundling or hosted distribution.
- Distinguish declared budget, observed requests, actual billing telemetry, estimates and unknowns. No savings or virality claim follows from a production receipt.
- A button, project export, example-only render, queued message or mocked execution does not satisfy integrated acceptance.

## Authorized parameters
DEFAULT_VIDEO_GENERATION_BUDGET_MINOR = 0

## Decision logic
| # | if | then |
|---|----|------|
| A | A paid generation endpoint is required under the local-only profile | Reject before invocation; require separate profile approval |
| B | Source facts, asset hashes or connection changes | Require a new request and context approval |
| C | A build may have completed without its response arriving | Inspect its saved build identity before retrying |
| D | Artifact checksum changes | Invalidate applicable publication approval |
