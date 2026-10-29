# Plan: ios-client
Spec: specs/ios-client.md
Architect verdict: PASS
Status: implementation underway and authorized by the owner's full-built-iOS instruction. Native app and simulator execution are proven for the merged review workflow; full workflow parity and physical-device acceptance remain incomplete.
Parent: platform-parity T4. Follow the existing standalone architecture and scoped CF implementation gates.

Current evidence (October 29, 2026): [PR 39](https://github.com/zrk222/WMM/pull/39)
merged as `7b44cd3572514cfb74543ad56f9cf26f14d6a20d`. Native
[run 40832996416](https://github.com/zrk222/WMM/actions/runs/40832996416)
built and executed the bundled engine on iPhone and iPad simulators: 25 tests per
family, zero failures and one physical-device-only skip. Windows/Ubuntu checks
passed. PostHog and Apple connector increments are separate candidates with their
own CI and workflow evidence. These results do not complete the unchecked T1-T14
requirements or prove physical-device, live-provider or full agent parity.

This verdict records the local architecture self-review: the selected embedding
and native boundaries preserve the required local ownership, operation coverage
and denial/recovery rules. It does not record independent human approval or
runtime feasibility results. The owner's explicit instruction to include a fully
built iOS app authorizes routine implementation of these packets. Do not add another
owner confirmation merely to begin code or build preparation. Credential issuance,
device access, publication and production actions retain their actual approval gates.

## Chosen architecture

Installable SwiftUI iOS/iPadOS application, bundled CPython shared domain engine,
in-process fixed operation bridge, local SQLite/media/jobs and native adapters.
No required desktop/Windows/WSL/Linux/remote WMM runtime. Optional provider APIs,
OAuth and storage remain optional integrations, with their own permission gates.
The shell must not fork domain policy into Swift or treat native calls as authority.

## Requirements-only packet completed before implementation

Owned tracked files: `specs/ios-client.md`, `plans/ios-client.md` only. Research,
source inventory, doctor, strict/validator/challenge and workflow observations
remain ignored under `.factory/ios-client`. The source seam inspection is read-only;
this requirements-only packet itself implemented no application code or Swift scaffold. Requirements
proof does not prove CPython imports, codec parity, Xcode builds or device execution.

Before local requirements commit run `specline validate ios-client --root .`,
`specline strict ios-client --root . --json`,
`specline verify-validators ios-client --root . --json`,
`specline challenge ios-client --root . --out .factory/ios-client/challenge.json`,
and the hash-bound workflow audit over these two documents and ignored evidence.
Strict or surviving requirement mutations block the requirements commit. Automated
gates never establish independent human architecture review or release approval.

## Implementation packets - all unchecked

- [ ] T1 | slice=mission_control | files=mission_control/ios_bridge.py,mission_control/ios_capabilities.py | verify=`python -m unittest tests.test_ios_contract_inventory -v` | Bind `ios_standalone`, `ios_reuse`, `ios_workflows`; split import-safe shared core and desktop-only modules, define fixed bridge and capability contracts. Supporting edits require separately reviewed file ownership and CF scope.
- [ ] T2 | slice=tests | files=tests/test_ios_contract_inventory.py,tests/test_ios_operation_conformance.py | verify=`python -m unittest tests.test_ios_contract_inventory tests.test_ios_operation_conformance -v` | Bind `ios_workflows`, `ios_authority`, `ios_agents`; enumerate the 53-operation floor plus owner/domain gaps and prove shared operation/denial fixtures for T1 and T5. This test packet runs with its implementation dependencies.
- [ ] T3 | slice=ios | files=ios/Build/Runtime.lock,ios/WMM.xcodeproj/project.pbxproj | verify=`xcodebuild -project ios/WMM.xcodeproj -scheme WMM -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' build CODE_SIGNING_ALLOWED=NO` | Bind `ios_standalone`, `ios_reuse`, `ios_native_gates`; pin toolchain and CPython source/framework hashes, package/sign required extensions and import the shared core. Build and runtime extension imports need simulator and device proof.
- [ ] T4 | slice=ios | files=ios/WMM/Identity/LocalIdentity.swift,ios/WMM/Identity/KeychainVault.swift,ios/WMM/Storage/LocalStore.swift,ios/WMMTests/StorageIdentityTests.swift | verify=`xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMCoreContract -destination "platform=iOS Simulator,id=$WMM_SIMULATOR_UDID" test` | Bind `ios_storage`, `ios_secrets`, `ios_authority`; implement protected container storage, atomic migration, Keychain namespaces/lock/recovery, enrollment and current session/role binding without duplicated domain state or plaintext fallback.
- [ ] T5 | slice=mission_control | files=mission_control/ios_operation_adapter.py | verify=`python -m unittest tests.test_ios_operation_conformance -v` | Bind `ios_workflows`, `ios_authority`, `ios_agents`; shared operation dispatch and grant/standing/review/commit guards with stale/foreign/revoked/expired/quota denial, using T2 conformance fixtures. No CLI subprocess or unverified subscription access.
- [ ] T6 | slice=ios | files=ios/WMM/Bridge/DomainBridge.swift,ios/WMM/Agents/ScopedAgentRuntime.swift,ios/WMMTests/BridgeAgentTests.swift | verify=`xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMCoreContract -destination "platform=iOS Simulator,id=$WMM_SIMULATOR_UDID" test` | Bind `ios_agents`, `ios_authority`, `ios_workflows`; native bridge, configured inference, bounded envelopes, cancellation and actual owner/agent parity through T5 guards.
- [ ] T7 | slice=ios | files=ios/WMM/Media/MediaIntake.swift,ios/WMM/Providers/ProviderTransport.swift,ios/WMM/Providers/ProviderAuthentication.swift,ios/WMMTests/ProviderIntakeTests.swift | verify=`xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMCoreContract -destination "platform=iOS Simulator,id=$WMM_SIMULATOR_UDID" test` | Bind `ios_media_intake`, `ios_provider_auth`; Photos/Files and original bytes/rights, optional Drive and selected BYOK/OAuth, callback/account/scope/refresh/revoke checks, permitted polling/import reconciliation. Provider approval is independent.
- [ ] T8 | slice=ios | files=ios/WMM/Media/TimelineRenderer.swift,ios/WMM/Media/MediaInspector.swift,ios/WMM/Studio/LocalStudio.swift,ios/WMMTests/MediaConformanceTests.swift | verify=`xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMCoreContract -destination "platform=iOS Simulator,id=$WMM_SIMULATOR_UDID" test` | Bind `ios_timeline`, `ios_studio`; native frame/effect/speed/audio inspection/composition/export and declarative Hypit-equivalent scenes, typed revisions, before/after preview and uncertain recovery. Unsupported templates/codecs stay blocking gaps; no required CLI/browser/companion renderer.
- [ ] T9 | slice=ios | files=ios/WMM/Jobs/LocalScheduler.swift,ios/WMM/Jobs/BackgroundExecution.swift,ios/WMMTests/LifecycleRecoveryTests.swift | verify=`xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMDeviceAcceptance -destination "platform=iOS,id=$WMM_DEVICE_UDID" test` | Bind `ios_background`, `ios_recovery`; durable leases/progress, optional eligible background APIs, kill/lock/expiration/memory/network failure, current authority before resume, cancellation and effect reconciliation. Test 17 baseline and 26 continued processing separately; no always-on guarantee.
- [ ] T10 | slice=ios | files=ios/WMM/Workflow/WorkflowNavigation.swift,ios/WMM/Reports/ReportExport.swift,ios/WMMTests/WorkflowParityTests.swift,ios/WMMUITests/AccessibleWorkflowTests.swift | verify=`xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMDeviceAcceptance -destination "platform=iOS,id=$WMM_DEVICE_UDID" test` | Bind `ios_workflows`, `ios_reports`, `ios_ui_access`; every owner stage/domain, editor/studio/grants/review/standing controls, telemetry/recovery and PDF/JSON/CSV/snapshot readback. Separately reviewed Prestige/accessibility gates precede UI work; prove iPhone and iPad controls.
- [ ] T11 | slice=tests | files=tests/ios_acceptance.md | verify=`python tools/check_platform_receipts.py --profile ios` | Trace every requirement to fresh standalone device procedures and artifacts, preserving Windows/macOS/Linux/Ubuntu scope and optional-provider evidence boundaries.
- [ ] T12 | slice=ios | files=ios/WMM.xcodeproj/xcshareddata/xctestplans/WMMCoreContract.xctestplan,ios/WMM.xcodeproj/xcshareddata/xctestplans/WMMDeviceAcceptance.xctestplan | verify=`xcodebuild -project ios/WMM.xcodeproj -scheme WMM -testPlan WMMDeviceAcceptance -destination "platform=iOS,id=$WMM_DEVICE_UDID" test` | Bind `ios_native_gates` and all 16 requirements; executable core and device plans with nonempty positive/negative fixtures. Test plans must be introduced with their dependent implementation packets before those test commands run.
- [ ] T13 | slice=tools | files=tools/check_platform_receipts.py | verify=`python tools/check_platform_receipts.py --profile ios` | Bind `ios_native_gates`; validate exact source/signed app/runtime/device/OS/SDK identities, xcresult and media/Keychain/lifecycle/accessibility/export artifacts; absence fails support claims.
- [ ] T14 | slice=.github | files=.github/workflows/platform-checks.yml | verify=`python tools/check_platform_receipts.py --ci-contract` | Bind `ios_native_gates`; execute declared Apple build/simulator profiles, retain actual-device evidence gaps and existing platform regressions. Full support stays incomplete until all required native/device gates pass.

The filenames above are proposed reviewed packet boundaries; they do not imply
existing modules or files. Their verification commands are NOT_RUN until targets,
test plans, native tools and authorized devices exist. UDID variables are supplied
from actual selected hardware/simulator inventories; no device identity is invented.
Source change, added domain or changed operation catalog invalidates the mapping
and requires a refreshed inventory, acceptance cases and candidate-bound receipts.

## Verification and review boundaries

Each implementation packet needs fresh CF doctor, scoped SSAT architecture and QA,
real domain/integration tests, meaningful source mutations, privacy and workflow
evidence before a local implementation-complete claim. Forge scaffold/fill/smoke
and native media/device gates are NOT_RUN for this requirements-only packet; no
dummy Swift targets or empty manifests may be used to manufacture a pass.

Current blocker: no macOS/Xcode host or iOS device in this environment. Requirements
can be validated locally; app compilation, signing, installation, Keychain lock
behavior, native media parity and on-device continuity cannot. App Store review,
provider OAuth permissions, provider outcomes and publication remain separate gates.
The contract preserves full requested scope even when a platform/provider adapter
is temporarily unavailable; that state is retained work, not a scope reduction.
