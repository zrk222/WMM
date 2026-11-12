# Plan: macos-desktop-preview
Spec: specs/macos-desktop-preview.md
Architect verdict: PASS

## Architecture
Use keyring's explicit macOS Keychain adapter under the existing Vault facade.
Stage the existing frozen engine and hash-bound native window in a standard app
bundle. Native CI artifacts remain separate from signed public distribution.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/macos_vault.py,mission_control/credential_vault.py,tests/test_macos_vault.py,tests/test_linux_vault.py | verify=`python -m unittest tests.test_macos_vault tests.test_linux_vault -v` | Select explicit native storage, scoped addresses, bounded JSON and redacted failures. Preserve rejection of other unsupported platforms.

  Create the Mac backend and its tests; modify the facade and unsupported-platform
  test. Covers `native_backend`, `scoped_item`, `payload_bound`, `keychain_failure`:
  construct only `keyring.backends.macOS.Keyring`, reset its keychain override,
  use the fixed service and SHA-256 account, and reject empty/control-character or
  over-2048-character addresses. Reject payloads over 2560 UTF-8 bytes, duplicate
  keys and non-finite constants at every nesting level. Missing adapters and denied
  read/write/delete operations must return redacted errors, preserve existing
  records and never fall back. Exact concurrent deletion stays idempotent.
- [ ] T2 | slice=tools | files=tools/build_desktop.py,tools/build_macos_package.py,tests/test_macos_package.py | verify=`python -m unittest tests.test_macos_package -v` | Reuse the native launcher in an app bundle without operational data or signing claims.

  Modify the existing builder; create the Mac stager and tests. Covers `app_bundle`:
  require regular WMM and WMM-Mission-Control executables plus `_internal` libraries.
  Put executables in Contents/MacOS and relocate `_internal` to Contents/Frameworks
  for the frozen bootloader. Set CFBundleExecutable=WMM-Mission-Control and
  LSMinimumSystemVersion=15.0. Reject missing libraries, existing destinations,
  absolute/external/dangling links. Preserve contained relative framework links
  and Unix modes in the archive; refuse archive replacement. Fixture checks verify
  staging and ZIP metadata; T4 verifies the actual re-extracted runtime.
- [ ] T3 | slice=tools | files=tools/check_macos_bundle.py,tools/test_native_desktop_bundle.py,tests/test_native_desktop_package.py,tests/test_desktop_entry.py | verify=`python -m unittest tests.test_macos_package tests.test_native_desktop_package tests.test_desktop_entry -v` | Record packaged lifecycle, native vault cleanup and rejected engine tampering on Mac. Isolate Mac test homes using their Application Support path.

  Create the Mac acceptance probe; modify existing isolation and entry tests.
  Covers `package_check`: refuse execution unless darwin, GITHUB_ACTIONS=true,
  RUNNER_ENVIRONMENT=github-hosted and WMM_MAC_PACKAGE_TEST=1. Pass only the
  environment allowlist; use disposable HOME and Application Support directories.
  Provision a disposable unlocked native test Keychain as the only searched
  Keychain. Use the runner's real home only for provisioning and the vault-only
  check, which does not open a workspace. Restore previous default/search-list
  settings and remove the fixture on success or failure. Record actual
  --check, --self-test and --vault-self-test output, asserting PASS and synthetic
  item removal. Verify the exact native pair starts and stops with zero queued
  jobs; an altered engine must exit 3 for digest mismatch before any workspace
  exists. Other failures cannot satisfy this assertion. The verifier emits only
  a startup/shutdown phase and a fixed reason token; the probe prints at most
  one matching failure line and never raw subprocess output. Retain failed Mac
  native-pair checks with run, attempt, source, architecture and both hashes.
  Run the existing synthetic first-packet/agent-setup smoke. No provider credentials.
- [ ] T4 | slice=.github | files=.github/workflows/macos-desktop.yml,tests/test_macos_package.py | verify=`python -m unittest tests.test_macos_package -v` | Build declared Mac architectures with pinned native Keychain dependency and retain receipts.

  Create the workflow and modify its source-contract test. Covers `mac_ci`:
  build (macos-15-intel, x86_64) and (macos-15, arm64) must both pass. Run Mac
  vault/package/Keychain-probe tests plus native helper and desktop entry tests.
  Install pinned native dependencies; build the real engine/window, archive,
  extract with ditto, then run T3 against the extracted app. Upload ZIP, build.json
  and acceptance.json for seven days with source SHA and actual architecture.
  Repository permission is contents:read; no public release job.
- [ ] T5 | slice=docs | files=docs/macos-desktop-preview.md,docs/requirements-macos.txt | verify=`python -m unittest tests.test_macos_package -v` | Pin native Keychain dependency and explain artifact, architecture, signing and acceptance boundaries.

  Create acceptance guidance and native dependency lock. Covers `release_boundary`:
  label artifacts unsigned, not notarized and not a human setup or live-account
  result. Never suggest bypassing Gatekeeper. No deletions or credential migration.

- [ ] T6 | slice=desktop | files=desktop/launcher/src/lib.rs,desktop/src-tauri/src/main.rs | verify=`rustfmt --check desktop/launcher/src/lib.rs desktop/src-tauri/src/main.rs` | Distinguish the typed pre-spawn digest refusal and emit bounded startup or shutdown failure diagnostics.

  Modify the launcher and native verification command only. Preserve readiness
  authentication, worker activation, deadline and shutdown semantics. Run the
  compiled launcher checks on both Mac architectures in T4 and Windows/Ubuntu
  native-package CI; rustfmt is a local syntax and formatting check.

## Gates
Save exact command output under `.factory/macos-desktop-preview/`; advancing a
phase requires its recorded PASS, not file presence.

1. Before edits: `factory doctor --strict --json` must report ok=true.
2. Contract: `specline strict macos-desktop-preview` must have zero warnings;
   `specline verify-validators macos-desktop-preview` must kill all eight mutants;
   `specline gate spec macos-desktop-preview` and `specline gate plan macos-desktop-preview`
   must seal current bytes. Retain strict, validator and seal outputs.
3. Source: run each task's unittest command, plus `tests.test_macos_keychain_probe`.
   `forge review macos-desktop-preview specs/macos-desktop-preview.ssat.yaml`,
   `forge arch-gate macos-desktop-preview specs/macos-desktop-preview.ssat.yaml`
   and `forge qa macos-desktop-preview --ssat specs/macos-desktop-preview.ssat.yaml --strict`
   must pass. Run `forge verify-tests
   macos-desktop-preview specs/macos-desktop-preview.ssat.yaml` then `forge smoke
   macos-desktop-preview` using the same process environment. Preserve logs and
   QA JSON; smoke proves only its named scoped-address/JSON scenario.
4. Native: both T4 architecture jobs must have successful source checks, build,
   extracted-app acceptance and artifact upload. Verify build.json/acceptance.json
   against the candidate SHA and archive digest. Never substitute fixture results.
5. Evidence: refresh candidate and artifact hashes in contract.json/observations.json
   in the evidence folder. `factory audit workflows --root . --contract
   .factory/macos-desktop-preview/contract.json --observations
   .factory/macos-desktop-preview/observations.json --json` must pass before merge.

Merge acceptance is bounded to source and headless native package checks above.
Mac window open/close, Finder launch, normal downloaded-app Gatekeeper launch and
independent first use remain NOT_RUN public-release gates. Close them on actual Mac
hardware with signed/notarized artifacts: launch normally, complete first packet,
close/reopen without losing data, and retain source-bound receipts. No paid
account creation or campaign activation is authorized by this implementation.
