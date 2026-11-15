# Spec: macos-desktop-preview
Status: approved

## MUST - Functional core
### Description
Build the existing desktop engine and native window as macOS app artifacts. Add
one explicit macOS Keychain backend; retain the existing workspace, authority,
loopback ownership and credential namespace. An unsigned CI artifact is not a
notarized public release or a human first-use result.

### Requirements (EARS)
- Where the operating system is macOS, the system shall select only the explicit macOS Keychain backend through `native_backend` and shall reject an unavailable backend without another credential store.
- The system shall store each native item using the fixed service Wize Marketing Machine and the SHA-256 of the existing scoped credential name through `scoped_item`.
- The system shall preserve bounded canonical JSON values with at most 2560 UTF-8 bytes through `payload_bound` and shall reject invalid or duplicate-key native JSON.
- If Keychain access is denied or unavailable, the system shall return a redacted unlock message without deleting saved workspace records through `keychain_failure`.
- The system shall emit the frozen engine and existing native window together inside a macOS app bundle through `app_bundle`, with durable data outside that bundle.
- The system shall reject an altered bundled engine before workspace creation and shall verify native Keychain round-trip cleanup through `package_check`.
- The system shall emit macOS Intel and Apple Silicon build artifacts with actual architecture, source hashes and synthetic lifecycle receipts through `mac_ci`.
- The system shall label macOS build artifacts as unsigned development previews with no notarization, independent human setup or live-provider acceptance claim through `release_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: native_backend
 Given macOS or a missing Keychain dependency
 When `native_backend` selects credential storage
 Then only the macOS Keyring adapter is constructed or setup fails closed
Scenario: scoped_item
 Given two distinct scoped credential names
 When `scoped_item` stores and reads them
 Then each exact hashed address remains separate
Scenario: payload_bound
 Given bounded or corrupt native JSON
 When `payload_bound` validates the payload
 Then oversized and duplicate-key values are rejected
Scenario: keychain_failure
 Given a locked or denied native backend
 When `keychain_failure` reads or writes a credential
 Then a redacted retry message is returned and no fallback runs
Scenario: app_bundle
 Given the existing frozen engine and native window
 When `app_bundle` checks the declared transition
 Then both executable files are inside the declared bundle directory and durable data is outside the app
Scenario: package_check
 Given the staged app bundle
 When `package_check` verifies the engine and native vault
 Then the exact engine starts and stops and the synthetic secret is removed
 And a changed engine is rejected before workspace creation
Scenario: mac_ci
 Given declared macOS Intel and Apple Silicon jobs
 When `mac_ci` finishes a package check
 Then the receipt records the actual architecture and source hash
Scenario: release_boundary
 Given a macOS CI artifact
 When `release_boundary` describes the artifact
 Then notarization and human or live-provider acceptance are not claimed
```

## SHOULD - Technical
- The explicit backend is `keyring.backends.macOS.Keyring`. The app bundle uses
  `Contents/MacOS` for both executables and the existing Application Support path
  for durable data.
- Import the explicit macOS backend directly; do not use global keyring selection,
  a shell command carrying secrets, environment-selected files or plaintext fallbacks.
- Reuse the Rust launcher and its authenticated sidecar protocol. No new server.
- Reuse existing native-vault self-test cleanup and packaged first-packet checks.
- Run native builds in GitHub runners, not on this Windows workstation.
- Windows signing and macOS Developer ID/notarization require owner-controlled
  signing identities; this feature neither creates nor purchases them.

## Authorized parameters
These retain the existing native-vault payload in bytes and subprocess timeout in seconds.
MAX_BYTES = 2560
timeout = 90
