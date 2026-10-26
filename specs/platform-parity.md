# Spec: platform-parity
Status: REQUIRED / IMPLEMENTATION INCOMPLETE
Requested: full WMM operation on iOS, Linux and Ubuntu; additive to all prior goal requirements.

## MUST - Functional core
### Requirements (EARS)
- The system shall return a current capability inventory for each declared platform profile covering owner setup, protected credentials, provider connections, uploads and optional Drive, viral discovery, full editing and stitching, native rendering, approvals, autonomous execution, telemetry, analytics and PDF/JSON export; each unexecuted acceptance shall remain NOT_RUN, identified by `platform_inventory`.
- The system shall store Linux and Ubuntu credentials in an explicitly selected native Secret Service backend with app/database namespace binding, reject locked or unavailable secret services without plaintext fallback, preserve existing records on errors and verify put/get/delete with synthetic secrets and cleanup, identified by `platform_linux_vault`.
- The system shall return native agent discovery, invocation, cancellation and results on Linux and Ubuntu using their installed supported Codex/Claude runtimes, preserving exact owner/grant/approval context and recording unsupported or unavailable runtimes without invented compatibility, identified by `platform_linux_agents`.
- The system shall return verified results and artifacts from executing the complete supported WMM owner and agent workflows on declared Linux and Ubuntu profiles with durable jobs, approved media editing/stitching/rendering and equivalent CLI/MCP controls, retaining the existing 67108864 bytes media limit and 60 seconds worker lease, identified by `platform_linux_workflows`.
- The system shall return all WMM workflow controls to iOS users through an authenticated supported client, including optional photo/file/Drive intake, video and audio preview, full creative settings, approval and scoped autonomous modes, live progress, cancellation, results and PDF export; viewport resizing alone shall not establish acceptance, identified by `platform_ios_workflows`.
- The system shall return independent on-device iOS operation with protected local identity, durable local jobs and platform-native media processing, rejecting any required remote WMM worker, Windows machine, Linux machine, paired computer or companion server as fulfillment of standalone operation, identified by `platform_pairing_boundary`.
- The system shall return durable workflow status and recovery after iOS suspension, screen lock, browser closure or transport interruption; supported background execution shall use actual local platform capabilities with explicit operating-system constraints and safe durable resume, never a required paired worker or an assumption of uninterrupted browser execution, identified by `platform_mobile_continuity`.
- The system shall emit platform-specific test and device receipts for complete workflows, credential lock/recovery, agent parity, accessibility and exports before claiming a profile supported; existing Windows behavior shall retain its regression gates, identified by `platform_acceptance`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: platform_inventory
  Given a declared operating profile
  When `platform_inventory` evaluates its capabilities
  Then each supported workflow links current observed evidence or an explicit missing state
Scenario: platform_linux_vault
  Given a Linux or Ubuntu native secret service
  When `platform_linux_vault` stores reads deletes and encounters a locked service
  Then protected scoped values round trip and failure preserves existing data without plaintext storage
Scenario: platform_linux_agents
  Given declared installed native agents
  When `platform_linux_agents` exercises guarded invocation and cancellation
  Then actual runtime and authority results are recorded
Scenario: platform_linux_workflows
  Given a declared Linux or Ubuntu installation
  When `platform_linux_workflows` runs the complete owner and agent journey
  Then actual production artifacts telemetry approvals and exports are verified
Scenario: platform_ios_workflows
  Given a supported iOS device and authenticated client
  When `platform_ios_workflows` exercises intake editing approval autonomous work and export
  Then every requested workflow is usable with device evidence
Scenario: platform_pairing_boundary
  Given an independently installed iOS client and local WMM execution engine
  When `platform_pairing_boundary` tests revoked or unauthenticated access
  Then unauthenticated operations are denied and no other-platform WMM host is required
Scenario: platform_mobile_continuity
  Given an active durable workflow
  When `platform_mobile_continuity` suspends or disconnects the iOS client
  Then reopening recovers actual retained progress without duplicate external effects
Scenario: platform_acceptance
  Given all declared supported profiles
  When `platform_acceptance` evaluates profile-specific receipts
  Then incomplete native or device checks prevent a full-support claim
```

## Architecture decisions and evidence boundaries
Standalone operation is mandatory on Windows, Ubuntu/Linux and iOS. Each installation owns its local data, protected credentials, execution engine, media processing, approvals, agent operations, telemetry and exports. No required Windows host, WSL bridge, Linux worker, paired desktop, remote WMM server or running installation on another platform is allowed. Optional third-party APIs and user-selected external storage remain optional integrations, not hidden WMM runtime dependencies. Cross-platform source libraries or build tooling do not count as runtime interdependencies.

A responsive web page, mobile viewport, remote-control client or paired-host demonstration cannot satisfy iOS acceptance. iOS requires an installable on-device application and local implementation of durable storage, Keychain credentials, native media editing/stitching/encoding, agent operations, authenticated approvals and actual-device lifecycle recovery. Do not promise uninterrupted background work beyond iOS capabilities; preserve queued work and resume safely when execution is permitted. Unsupported third-party CLI binaries need verified native/API adapters on that platform, not claims of CLI compatibility.

Current source inspection (October26): Windows Credential Manager and Linux Secret Service backends exist, with isolated Ubuntu keyring acceptance; that proves only scoped protected storage. Native agent discovery still searches Windows paths. The repository has no iOS app target or Swift sources. Existing Python/FFmpeg processes and desktop Chromium checks do not prove iOS operation. Complete standalone Windows/Linux/Ubuntu/iOS profile acceptance remains unproven. Earlier macOS requirements remain additive and must not be removed.

Official references reviewed for architecture (not execution evidence):
Ubuntu Security FAQ: https://wiki.ubuntu.com/Security/FAQ describes GNOME Keyring integration with SecretService.
GNOME keyring help: https://help.gnome.org/seahorse/keyring.html describes application secrets in keyrings.
Apple background guidance: https://developer.apple.com/documentation/uikit/preparing-your-ui-to-run-in-the-background describes limited normal execution after entering background.
Apple background strategies: https://developer.apple.com/documentation/BackgroundTasks/choosing-background-strategies-for-your-app describes explicit platform background strategies.

## WON'T - Out of scope of this requirements packet
No platform is marked supported by this document. No implementation, device result, migration, deployment or measured performance result is implied.

## Independent runtime acceptance matrix
For each Windows, Ubuntu/Linux and iOS profile, test a fresh install with every other WMM platform offline. Prove local storage and restart, protected credential create/read/lock/recovery/delete, optional Drive/local UGC intake, exact viral qualification, complete editing/stitching/audio/render/preview/export, human and scoped-agent/autonomous operations, current approvals, telemetry/cancel/recovery, complete analytics and PDF/JSON/CSV. Record exact source hashes, runtime/OS/device/build identity and artifacts. Any missing workflow or required off-device WMM process prevents full-support status. Optional provider account availability is reported separately.
