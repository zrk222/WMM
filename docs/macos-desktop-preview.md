# macOS desktop build acceptance

The macOS workflow builds separate Intel and Apple Silicon app artifacts from
the same WMM source. It reuses the native Mission Control window, authenticated
engine startup, loopback listener and private workspace. Provider credentials
use the explicit macOS Keychain backend; there is no file fallback.

These are **unsigned development artifacts**, not a notarized public Mac release.
Do not disable Gatekeeper or remove quarantine flags to open them. A CI pass
does not prove Finder launch, first-time user setup, live account access, or
marketing outcomes. Read the architecture and source-bound receipt beside each
artifact before using its engineering evidence.

The build currently targets macOS 15 or later. Intel and Apple Silicon are
separate artifacts; neither requires a Windows or Linux WMM installation.
Workspace data remains under `~/Library/Application Support/Wize Marketing Machine`,
outside the app bundle. Keychain access can require unlocking or OS consent.
An update does not copy credentials to another machine or widen provider access.

## Required before public distribution

- Successful native builds and Keychain cleanup on each declared architecture.
- Native window and first-packet acceptance on actual Mac hardware.
- Owner-controlled Developer ID signing and Apple notarization, followed by
  a normal downloaded-app launch with Gatekeeper protections intact.
- Explicit approval for a separately verified public Mac release.

The existing Windows/Ubuntu desktop release workflow does not publish these Mac
artifacts. Windows publisher signing remains a separate identity and check.

References: [keyring native backends](https://keyring.readthedocs.io/en/latest/),
[Tauri macOS signing](https://v2.tauri.app/distribute/sign/macos/).
