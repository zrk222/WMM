# Spec: ios-client
Status: REQUIREMENTS CANDIDATE / IMPLEMENTATION AND DEVICE ACCEPTANCE NOT_RUN
Parent: platform-parity T4; additive to every accepted WMM requirement.
Baseline inspected: 91c59d3. This packet changes no runtime source or app target.

## MUST - Functional core
### Requirements (EARS)
- The system shall return an installable standalone iOS application owning its local WMM domain engine, storage, jobs, identity, media processing and exports, with no required Windows, WSL, Linux, desktop, remote WMM worker or companion server, identified by `ios_standalone`.
- The system shall execute the shared WMM Python domain and operation contracts through a bundled CPython embedding bridge and typed native adapters, reject platform-restricted subprocess and downloaded executable-code paths, and retain one authoritative domain implementation, identified by `ios_reuse`.
- The system shall return an operation inventory covering the 53 baseline catalog operations, the 12 owner stages and every additional accepted domain workflow, retain existing incomplete catalog coverage as implementation obligations, and reject missing operation mappings as incomplete parity, identified by `ios_workflows`.
- The system shall enforce local authenticated owner identity, distinct human review where required, current app and resource revisions, scoped agent grants with 1 through 10000 calls and at most 24 hours lifetime, revocation, immutable approval envelopes and standing authority at admission and commit, identified by `ios_authority`.
- The system shall store app-scoped SQLite data, immutable evidence history, media bytes, durable jobs and recovery checkpoints inside the application container with atomic migrations and explicit local backup and restore, preserving prior records and hashes on interrupted or invalid migration, identified by `ios_storage`.
- The system shall store provider secrets, local identity keys and grant material in app and database scoped Keychain items with explicit accessibility policy, deny locked or unavailable protected access without plaintext fallback, and verify create read lock recovery delete and cleanup, identified by `ios_secrets`.
- The system shall admit user-selected Photos and Files uploads and optional Drive intake through native permission and storage adapters, preserve the 67108864-byte managed-media bound, exact source bytes and current reuse attestations, and deny foreign stale revoked or unverified reuse inputs, identified by `ios_media_intake`.
- The system shall execute the shared video timeline contract through local AVFoundation composition and encoding adapters with source-frame trims, ordering, split, transforms, speed, effects, retained or muted audio, revision history and undo redo, and return validated decoded outputs before reporting render completion, identified by `ios_timeline`.
- The system shall preserve declarative Hypit production and studio plan start inspect edit close workflows through a local native studio and renderer with current source versions, typed parameter edits, before and after preview artifacts and uncertain-result recovery, identified by `ios_studio`.
- The system shall return the shared agent tasks and scoped human and agent operation semantics through an on-device dispatcher and configured supported inference adapters, reject desktop CLI execution and unverified subscription access, and keep provider-model availability distinct from local WMM engine availability, identified by `ios_agents`.
- The system shall return protected BYOK setup and optional provider-approved OAuth through native networking and authentication adapters with exact account scope, callback validation, reconnect and revocation states, while requiring no external WMM runtime for local workflows, identified by `ios_provider_auth`.
- The system shall execute eligible work only during foreground or actual operating-system granted background runtime, persist checkpoints on expiration or cancellation, expose deferred state when execution is unavailable, and reject uninterrupted-daemon or exact-time background execution claims, identified by `ios_background`.
- The system shall return durable progress, cancellation, failure and recovery after suspension, screen lock, force termination, network loss or uncertain provider results using retained operation identities, the existing 60 seconds job lease and at most 3 attempts without duplicate external effects, identified by `ios_recovery`.
- The system shall return the shared discovery, experiment, subscription, cohort, funnel, acquisition, attribution and learning analytics with observed evidence and unknown denominators preserved, and export app-scoped PDF JSON CSV reports and portable snapshots without credentials, identified by `ios_reports`.
- The system shall expose every required owner and admitted agent workflow through native iPhone and iPad navigation and accessible touch keyboard and VoiceOver controls, preserve upload preview editing approval telemetry recovery and report operations, and reject viewport-only demonstrations as iOS acceptance, identified by `ios_ui_access`.
- The system shall emit source-bound Xcode simulator and physical-device receipts for fresh standalone install, shared-domain conformance, Keychain, media, authority, lifecycle, accessibility and exports before marking an iOS profile supported, retaining absent Apple-host or device evidence as NOT_RUN, identified by `ios_native_gates`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: ios_standalone
  Given a fresh installed WMM iOS app with every other WMM installation offline
  When `ios_standalone` prepares a local campaign and edits renders and exports its media
  Then the local engine completes without a paired computer or external WMM process
  And optional provider disconnection does not disable local storage editing or reports
Scenario: ios_reuse
  Given bundled shared domain fixtures and a signed embedded interpreter
  When `ios_reuse` exercises domain operations and attempts an arbitrary subprocess
  Then accepted domain results match the shared canonical contracts
  And the subprocess is denied without invoking a desktop process or downloading code
Scenario: ios_workflows
  Given the baseline catalog and twelve-stage owner workflow inventory
  When `ios_workflows` compares every required operation with the iOS mapping
  Then each operation has a local implementation packet and an acceptance case
  And an omitted operation or unresolved mapping prevents full parity
Scenario: ios_authority
  Given an app-scoped grant and an immutable independently reviewed operation
  When `ios_authority` encounters a changed revision or expired revoked foreign or exhausted grant
  Then execution is denied at admission and commit and existing evidence remains intact
  And the acting agent cannot approve its own request or widen standing authority
  And grant issuance retains 1 through 10000 calls and at most 24 hours lifetime
Scenario: ios_storage
  Given a synthetic local database with evidence revisions jobs and source media
  When `ios_storage` restarts and encounters an interrupted migration or invalid restore
  Then committed data and historical hashes survive and invalid writes roll back
  And restored data does not restore authority from stale session or process identifiers
Scenario: ios_secrets
  Given synthetic Keychain items scoped to two app and database identities
  When `ios_secrets` creates reads locks recovers deletes and repeats the reads
  Then authorized reads round trip and foreign or locked access is denied
  And deletion is verified without exposing secrets in logs reports or snapshots
Scenario: ios_media_intake
  Given selected Photos Files and configured Drive sources with current reuse evidence
  When `ios_media_intake` imports within 67108864 bytes and encounters revoked foreign or changed source bytes
  Then original valid bytes are retained with identities and invalid reuse is denied
  And permission denial or Drive disconnection preserves current local media
Scenario: ios_timeline
  Given a shared frame-based project with two synthetic picture and audio sources
  When `ios_timeline` trims reorders splits transforms changes speed edits effects and performs undo redo
  Then decoded export order frames dimensions duration and retained or muted audio match the project contract
  And stale rights or unavailable encoding prevents a completed-render claim
Scenario: ios_studio
  Given a declarative production project and an exact source and parameter revision
  When `ios_studio` plans starts inspects edits previews and closes the local session
  Then source and preview revisions agree and before and after artifacts remain inspectable
  And suspension or an uncertain edit reconciles before any repeated submission
Scenario: ios_agents
  Given the same task and operation envelopes for an owner and an admitted agent
  When `ios_agents` invokes configured inference and encounters an unavailable desktop CLI subscription route
  Then local dispatch retains the shared scope review cancellation and result rules
  And unavailable provider access is explicit without substituting subscription or API entitlement
Scenario: ios_provider_auth
  Given a configured BYOK account or a separately permitted OAuth integration
  When `ios_provider_auth` receives a mismatched callback missing scope or revoked credential
  Then the connection remains unavailable until the exact account is reviewed and reconnected
  And local WMM workflows continue without a remote WMM host
Scenario: ios_background
  Given a queued local job and an eligible operating-system background opportunity
  When `ios_background` is deferred expires or is cancelled by the user
  Then the app preserves its checkpoint and truthful deferred or cancelled state
  And reopening resumes eligible work without claiming uninterrupted background execution
Scenario: ios_recovery
  Given a durable job with an exact request key source revision and retained effect receipt
  When `ios_recovery` locks suspends terminates disconnects and reopens the application
  Then expired leases and uncertain results are reconciled with current authority before retry
  And cancellation retains actual completed effects while preventing duplicate submission
  And recovery preserves the 60 seconds lease and at most 3 attempts
Scenario: ios_reports
  Given observed app-scoped events and an unobserved attribution denominator
  When `ios_reports` computes analytics and exports PDF JSON CSV and a portable snapshot
  Then exported evidence agrees with the shared calculations and unknown values stay unknown
  And reports contain no credentials and pages contain at most 1000 report rows
Scenario: ios_ui_access
  Given an installed iPhone or iPad app with required workflow fixtures
  When `ios_ui_access` navigates intake production review cancellation recovery and export using VoiceOver touch and keyboard
  Then controls have usable labels focus and recoverable errors with actual preview and report readback
  And responsive screenshots alone do not establish workflow acceptance
Scenario: ios_native_gates
  Given an iOS support claim and its exact app source runtime and device identities
  When `ios_native_gates` encounters a missing physical-device or independent-install receipt
  Then the affected profile remains NOT_RUN or incomplete and full support is denied
  And requirements validation is never reported as an Xcode build or device execution
```

## Architecture decision - reuse the domain, replace restricted native seams

Choose a SwiftUI installable application with an embedded, signed CPython 3.14
XCFramework and bundled WMM Python code. This is a reviewed architecture candidate,
not proof that current eager imports or binary dependencies run on iOS. T1 and T3 must pin
the exact CPython patch/source/toolchain hashes and build an importable iOS module
closure before T2 implements workflows. Use an Objective-C/C embedding boundary
behind a serialized native actor; all Python/SQLite domain transactions use the
shared validators and authority guards, off the UI main thread. Native callbacks
return bounded typed data or app-owned file handles, never executable snippets.

The application carries its own interpreter and domain code; no Python installer,
pip, shell, external package server or WMM HTTP server is required at runtime.
App build tooling on macOS is a build dependency, not a runtime companion. The
first declared deployment floor is iOS/iPadOS 17.0; an additional iOS/iPadOS 26
profile may use continued-processing APIs only after its own device gates. Exact
tested OS patch, Xcode, SDK, Python and device model become receipt identities.
Changing the deployment floor requires a reviewed contract change.

Use SwiftUI screens and native pickers rather than requiring a browser or an
always-on loopback server. Reuse shared view-model data and canonical JSON
contracts through an in-process transport; do not duplicate domain calculations
or bypass `operation_authority`, grant, review or automation admission. The bridge
accepts only fixed operation envelopes, at most 1048576 JSON bytes, with larger
media passed as scoped app-owned resources. A native caller is not automatically
an authenticated owner. Optional external automation must use an explicitly
enabled authenticated transport with the same scope and revocation rules; no
publicly bound listener, desktop MCP process or stdio subprocess is required.

Keep the existing CLI/MCP clients on their supported platforms. iOS supplies an
equivalent typed on-device operation interface to its agent runtime; protocol
conformance fixtures must demonstrate semantic parity, not pretend that iOS
launched those CLI executables. Any optional connector or shortcut entry point
must undergo separate admission and cannot create human approval.

## Required coverage inventory - no workflow is removed

The baseline `mission_control/operation_catalog.py` contains 53 operations and
explicitly reports `full_agent_operation=False`. Inventory equality is a floor,
not full-domain acceptance. T1 freezes the actual current operation names, domain
descriptors and source hashes; later accepted operations extend this floor. Missing
agent operations remain required work; they cannot be hidden by calling an owner
screen or a reduced catalog complete. The future inventory must also enumerate
owner-only routes in `server.py` and their existing domain services.

| Required domain | Baseline catalog operation IDs | Additional owner and accepted scope retained |
| --- | --- | --- |
| Workspace and stages | `workspace.read`, `evidence.save`, `pipeline.prepare`, `jobs.read`, `job.cancel`, `operations.read` | App create/setup/switch, records, twelve stages, current proof, repairs, schedules, workflow feedback and policy |
| Discovery | `discovery.history`, `discovery.read`, `discovery.review`, `discovery.collect`, `discovery.watch`, `discovery.attempt`, `discovery.handoff` | Collections, rights, failed reads, observation expiry; 100000 views AND 10x documented comparable creator baseline; 1x-20x research filters never weaken qualification; UGC remains exempt |
| Local production | `media.sources`, `native.read`, `native.queue`, `hypit.read`, `hypit.queue` | Authentic assets, local UGC uploads and optional Drive, creative library/analysis/briefs/taste, reusable source and app proof, packaging variants/scripts/shot lists/previews and cutdowns |
| Frame editor | `editor.list`, `editor.read`, `editor.save`, `editor.edit`, `editor.history`, `editor.diff`, `editor.renders`, `editor.queue` | Full timeline settings, picture/audio stitching, preview, artifact verification, undo/redo, stale/revoked source denial |
| Studio | `studio.plan`, `studio.start`, `studio.sessions`, `studio.read`, `studio.edit`, `studio.inspect`, `studio.close` | Source hash/version ledger, exact parameter commands, own local session, diagnostics, restart and uncertain edit recovery |
| Funnel | `funnel.list`, `funnel.review`, `funnel.read`, `funnel.save`, `funnel.observations`, `funnel.import`, `funnel.report` | Audience/problem research, attributable app visits/install/activation/trial/paid/renewal, missing denominators and evidence |
| Subscription/customer | `growth.read`, `growth.history`, `growth.save`, `customer.history`, `customer.save` | Readiness, pricing/revenue journey, qualitative research, failure recovery, experiments and review history |
| Measurement and experiments | `measurement.read`, `cohort.define`, `events.import`, `billing.save`, `experiment.register`, `experiment.evaluate`, `experiment.action` | Payment/refund reconciliation, retention/contribution, attribution, acquisition/ASA/AEO, learning, page/weekly reports and results |
| Portable data | `snapshot.export` | Snapshot restore, PDF/JSON/CSV, media/source history, privacy and safe overwrite/merge decisions |
| Identity/connections/agents | Existing dedicated owner/grant/review/provider routes remain outside the baseline finite operation catalog | Local identities and roles, exact approvals, grants/revocation/standing authority, agent setup/tasks/usage/checkpoints, provider credentials/status/reconnect, consent and budgets |

Provider connection and publication state, provider-side OAuth/derived-metric
permission, app review and actual outcomes remain independent evidence. No
advertising spending or publication is enabled by this packet. Existing authorized
provider effects retain their exact review, idempotency and readback requirements.

## Native seam mapping and denied/unavailable recovery

| Current source seam | Required local iOS adapter | Denied/unavailable behavior and required proof |
| --- | --- | --- |
| `credential_vault.py` Windows Credential Manager/Linux Secret Service selection | Keychain Services, database/app/provider namespace, device-bound accessibility chosen in T2 | Locked access yields protected-data unavailable; preserve data, pause job, request foreground unlock; no file/env fallback |
| `worker.py` polling thread and 60-second SQLite lease | In-process durable scheduler with foreground and OS-granted execution windows | No continuous daemon; retain request identity, lease, attempts and progress; reconcile before retry after expiration |
| `agent_native.py`, `agent_process.py`, CLI package/binary discovery | Native inference/provider adapter plus the shared on-device operation dispatcher | No Codex/Claude/Kimi desktop binaries or stolen subscription tokens; explicit unsupported provider route, safe alternative only by owner selection |
| `media_native.py`, `managed_media_validation.py`, `hypit_media.py`, FFmpeg/FFprobe subprocesses | AVAssetReader/AVAssetWriter and AVFoundation inspection/composition, Core Image/Core Animation and VideoToolbox as required | Decoder/encoder/glyph/resource limits yield unavailable with retained sources; no synthesized metadata or completed artifact |
| `video_edit_rendering.py` filter/encoder argv | Shared frame plan mapped to AVMutableComposition, native transforms/effects and audio processing | Preserve 24 fps frame math, shape/raster/color/crop/rotation/fit, 25-400 percent speed in 25-percent steps and declared audio; test every accepted command |
| `hypit_authoring.py`, `hypit_runtime.py`, `hypit_studio_process.py`, browser/CLI/process/port controls | Native local declarative scene compiler, typed parameter broker and revisioned preview/export session | No arbitrary user code; preserve scene/text/font/timing/layout semantics and source ledgers; an unsupported template remains a blocking parity gap, not removed scope |
| File paths, symlinks, upload and Drive browser loopback callbacks | App-container file handles, Photos/Files selection, scoped URL access, native HTTPS/auth session | Copy selected bytes into owned storage; permission loss/cancel/expired token preserves existing imports; cloud file absence is explicit |
| Provider HTTP/signing and webhook listeners | Native URLSession and Keychain signing/auth adapters with exact provider contracts | Optional API accounts remain external providers; no required remote WMM worker; unavailable inbound delivery needs permitted polling/import plus duplicate-proof reconciliation before parity acceptance |
| PDF/browser print and downloads | Native PDF generation/share sheet plus shared canonical JSON/CSV/report calculations | Export failure retains local report; preview and reopened exported bytes must match source evidence |

This table chooses adapter boundaries, not untested API equivalence. Codec and
effect parity must be demonstrated for the complete accepted scene/timeline
surface, including retained audio, original fonts and international-text limits;
unsupported capabilities must stay visible and block the affected support claim.
No restriction grants permission to drop an operation or silently weaken a bound.

## Durable state, identity and lifecycle rules

Use one local database namespace per installation with app-owned media and
atomic writes; keep the existing domain schemas and append-only contracts. The
native shell provides protected container locations, not a parallel Swift data
model. SQLite WAL/checkpoint and file-protection settings need lock/kill/restart
tests before adoption. Backups and exports exclude secrets, bearer material,
ephemeral runtime authority and private diagnostics. Restore preserves unreadable
history and fails atomically instead of deleting or re-keying it to clear errors.

Keychain items default to `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`; a
background credential policy is separately owner-selected and tested before use.
Credentials never enter JavaScript, prompts, shared report data or diagnostics.
If protected data is unavailable, durable work waits for unlock. Deleting a local
secret does not assert remote provider revocation. Native local identity uses
Keychain-backed enrollment and current role/session state; LocalAuthentication
may unlock an identity but is not evidence of a distinct independent checker.

Foreground scheduling is the guaranteed application path. `BGProcessingTask`
and `BGAppRefreshTask` are opportunistic opportunities, not periodic schedulers.
`URLSession` background transfers may carry eligible provider files; admission
and completion recheck current authority and reuse rights. On the separately
tested iOS 26 profile, `BGContinuedProcessingTask` is only for an eligible
foreground user-initiated task, with reported progress, cancellation, expiration
and device/resource eligibility. Autonomous standing-authority jobs must not
impersonate foreground user action to obtain that API. No silent-push server,
audio/location abuse or keepalive is required for standalone operation.

OS suspension does not mean a job completed. Persist its last committed progress,
request key, source hashes, attempts, effect intent and any actual provider receipt.
On reopening, recover the shared 60-second lease and retry ceiling without
resubmitting an uncertain effect. Recheck current grants/approval/reuse before
continuing; authority never resurrects from PID, origin, notification or saved
native session. Force-quit may prevent background execution; retain durable local
work for a later permitted execution opportunity and show that constraint.

## Official basis reviewed October 26, 2026

The following support architecture feasibility and restrictions; none establish
that WMM has compiled or run on iOS. Apple Markdown documentation was read from
its linked official developer documentation endpoint when HTML required JavaScript.

[CPython 3.14 iOS embedding](https://docs.python.org/3.14/using/ios.html): bundle
  the interpreter, standard library and app code; use device/simulator XCFramework
  slices and packaged/signed extension frameworks. Full Xcode on macOS is needed
  to build. Its testbed can exercise library tests on the simulator. T1 must verify
  required extension modules and framework/privacy-manifest packaging.
[CPython subprocess availability](https://docs.python.org/3.14/library/subprocess.html):
  subprocess execution is unsupported on iOS. Desktop CLI launchers cannot be reused
  as runtime adapters.
[Apple background strategies](https://developer.apple.com/documentation/backgroundtasks/choosing-background-strategies-for-your-app):
  background runtime is limited or scheduled by the operating system; expiration
  must end or defer work, and background file transfers have a dedicated mechanism.
[Apple continued processing](https://developer.apple.com/documentation/backgroundtasks/performing-long-running-tasks-on-ios-and-ipados)
  and [WWDC25 background tasks](https://developer.apple.com/videos/play/wwdc2025/227/):
  the iOS 26 opportunity starts with foreground user action, reports progress and
  can be cancelled or denied resources. This is not an always-running agent daemon.
[AVMutableComposition](https://developer.apple.com/documentation/avfoundation/avmutablecomposition)
  and [AVAssetExportSession](https://developer.apple.com/documentation/avfoundation/avassetexportsession):
  native composition supports time-range/track editing and export sessions produce
  specified formats. Exact WMM frame/audio/codec/effect equivalence still needs tests.
[Keychain Services](https://developer.apple.com/documentation/security/keychain-services):
  native protected storage supplies the secret adapter; WMM namespacing, accessibility
  policy and lock/recovery behavior remain implementation and device-test obligations.
[Apple App Review Guidelines 2.5](https://developer.apple.com/app-store/review/guidelines/#software-requirements):
  bundle-contained code, public APIs and intended background-service use constrain
  distribution. WMM will bundle its executable logic and treat provider responses,
  declarative scenes and imported documents as data; no remote-code capability or
  App Review approval is inferred.

## WON'T - Scope of this requirements packet

No Swift/Xcode scaffold, shared-core refactor, device support, provider OAuth
permission, native media parity, performance measurement or App Store submission
is implemented here. Existing Windows/macOS/Linux/Ubuntu requirements remain
additive. All proposed iOS runtime gates below are NOT_RUN because this environment
has neither an Apple build host nor an attached iOS device.

## Native support gates - initial packet and current evidence

The table below retains the requirements packet's initial observations, not the
current implementation inventory. The native Swift application, Xcode target,
embedded Python engine and simulator test plans now exist. For the merged review
workflow, [run 40832996416](https://github.com/zrk222/WMM/actions/runs/40832996416)
at `107211626bcd47cec54d4fa6c659b5484bf543bf` passed on both iPhone and iPad
simulators (25 tests each, zero failures, one physical-device-only skip).
[PR 39](https://github.com/zrk222/WMM/pull/39) records the corresponding merge.
Physical-device and complete workflow acceptance are still required; the
simulator result does not supply those observations. Later candidates require
their own current source-bound results.

Run on a declared macOS host with full Xcode after implementation. Proposed target:
`ios/WMM.xcodeproj`, scheme `WMM`, device baseline 17.0 and additional 26 profile.
These paths are implementation packet targets, not files that currently exist.
Record source/tree hashes, exact Xcode/SDK/macOS/CPython/OS/device identities,
signature/bundle identity, commands, xcresult and decoded/exported artifacts.

| Gate | Exact command or required execution | Current state |
| --- | --- | --- |
| Toolchain | `xcodebuild -version`; `xcrun --sdk iphoneos --show-sdk-version`; `xcrun simctl list devices available` | NOT_RUN: no Apple host |
| Simulator build | `xcodebuild -project ios/WMM.xcodeproj -scheme WMM -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath .factory/ios-sim build CODE_SIGNING_ALLOWED=NO` | NOT_RUN: no target or Xcode |
| Physical build | `xcodebuild -project ios/WMM.xcodeproj -scheme WMM -sdk iphoneos -destination 'generic/platform=iOS' -derivedDataPath .factory/ios-device build` | NOT_RUN: signing and device build absent |
| Shared core and native bridge | `xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMCoreContract -destination "platform=iOS Simulator,id=$WMM_SIMULATOR_UDID" -resultBundlePath .factory/ios-core.xcresult test` | NOT_RUN: test plan and simulator absent |
| Physical full workflow | `xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMDeviceAcceptance -destination "platform=iOS,id=$WMM_DEVICE_UDID" -resultBundlePath .factory/ios-device.xcresult test` | NOT_RUN: no device; UDID must identify actual authorized device |
| Lifecycle/media/identity | Physical test plan plus manual lock, force-quit, denied permission, expired/revoked/foreign authority, real file/Photos/Drive and decoded picture/audio before/after receipts | NOT_RUN: simulator cannot substitute for these device results |
| Accessibility/export/independence | VoiceOver/touch/keyboard on iPhone and iPad, PDF/JSON/CSV/snapshot reopened, every other WMM installation offline, optional provider network tested separately | NOT_RUN: screenshots or catalog enumeration are insufficient |

Simulator and actual-device receipts are distinct. A successful build is not
installation, permission, lifecycle, media or provider proof. Any missing required
workflow, mandatory off-device WMM dependency or absent device gate prevents an
iOS support claim; a truthful unavailable state does not complete that obligation.
