# Spec: hypit-workflow-interface
Status: draft

## MUST - Functional core
### Description
Expose durable Hypit jobs as a user-selectable local production route and as
governed agent operations. Preserve native video behavior, actual source and
artifact validation, app scope and publication boundaries.

### Requirements (EARS)
- The system shall return saved Hypit artifacts and attempts in the selected workspace without executing a render through `workspace_history`.
- The system shall queue an exact current brief through the human interface and scoped agent operation using the same Hypit service through `shared_queue`.
- The system shall return verified selected-app video bytes for browser preview, download and byte seeking and reject foreign or changed artifacts through `artifact_delivery`.
- The system shall display native screens and Hypit caption composition as selectable production options for 15, 30, 45 or 60 seconds with explicit output and setup explanations through `renderer_choice`.
- The system shall expose fixed Hypit history and queue tools to CLI and MCP and reject ungranted operations or unsupported request fields through `agent_interface`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: workspace_history
  Given saved Hypit work in one app
  When `workspace_history` is loaded
  Then only that app history is returned without a new runtime invocation
Scenario: shared_queue
  Given an approved current video brief
  When `shared_queue` is requested through a human session and agent grant
  Then both use the same idempotent durable job contract
Scenario: artifact_delivery
  Given saved checksum-verified output
  When `artifact_delivery` is previewed or downloaded
  Then actual bytes and seeking are served and foreign or changed artifacts are rejected
Scenario: renderer_choice
  Given native and Hypit production options
  When `renderer_choice` is selected
  Then the submitted route matches the chosen renderer and its explanation describes the actual output
Scenario: agent_interface
  Given CLI and MCP calls with an ungranted or malformed operation
  When `agent_interface` validates the call
  Then no render or authority is created
```

## SHOULD - Technical
- Use HypitRenders and existing HTTP video range handling. The Hypit option is
  caption-only composition at this stage; approved app-screen rendering remains
  the native option. Shared editing and richer media remain required by UPG-07.
- Discovery reports executable presence separately from actual runtime readiness;
  loading workspace must not start Hypit or contact providers. Setup failures
  preserve native rendering and other workspace data.
- The generic job endpoint cannot bypass brief validation by passing hypit_render.
  Agent queue operations remain local preparation under existing grants and
  owner-selected checkpoint policy. They confer no publication/spend authority.
- UI status and preview retain visual review requirements and interrupted-build
  inspection guidance. Use native HTML controls, escaped content, keyboard
  navigation and accessible inline errors; validate desktop/mobile rendering.
- CLI subprocess acceptance uses timeout=30 seconds to bound the actual local
  client test. This test-runner limit is distinct from the owned render timeout.

## Authorized parameters
timeout = 30
