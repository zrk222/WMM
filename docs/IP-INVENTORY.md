# IP component inventory

**Status: source inventory recorded; release contents, ownership and relicensing review open.**
This is not a chain-of-title opinion, trademark clearance or commercial
relicensing permission.

Machine-readable inventory: [`ip-inventory.json`](ip-inventory.json)
Inventory SHA-256 (UTF-8, LF): `98e43d3a2409efcc5da9b089750d8e972171747303781762e4fd2d5d1e06bf3e`
Components: **538** (418 Rust crates, 101 npm build/test packages, 8 Python/runtime
entries, 7 system/build entries, 3 first-party entries and 1 vendored JS library).

## Shipment model

This source inventory distinguishes candidate installer contents, required host
packages, build tools and separately published documentation. The installer
build inputs are WMM source and static assets, CPython and selected Python
dependencies, and the Rust launcher and window dependencies.

- The Ubuntu installer declares fourteen host packages in
  [its base control file](../packaging/linux/control), including FFmpeg, DejaVu
  fonts, GNOME Keyring and D-Bus. The native desktop package adds
  `libwebkit2gtk-4.1-0` when the native launcher is present. Both lists are in
  the JSON; installed versions and license receipts remain to be reconciled.
- WebKitGTK is a Linux build/runtime input; Microsoft Edge WebView2 is
  system-provided on Windows. Neither is listed as a bundled file.
- The vendored Three.js bundle, synthetic screenshots and preview video are
  reviewed as public documentation assets. Build and test tools such as npm,
  Playwright, Remotion and Inno Setup are separate from the installed payload.

Use the machine inventory for declared license values and evidence paths. Its
counts describe the source inventory's classifications. Check the actual
installers and separately distributed assets before calling that inventory
complete or making an IP clearance decision.

## Open items

1. **Chain of title:** per-file ownership and contributor permission after the
   Apache-2.0 transition are not established.
2. **Agent-assisted work:** human contributions, tool terms, input sources and
   suspected copied material are not fully recorded.
3. **Icon provenance:** the desktop icons have no source receipt.
4. **Remotion:** confirm the applicable license for the rendered docs video.
5. **FFmpeg:** confirm the exact Ubuntu build license and configure flags.
6. **WebKitGTK:** confirm LGPL distribution obligations for the packaged runtime.
7. **Inno Setup:** retain its license and installer attribution requirements.
8. **Exact release binding:** bind this inventory to the release candidate SBOM
   and shipped payload hashes. A build-environment SBOM alone is insufficient.

## Updating this source inventory

1. Generate Cargo metadata for both manifests with `--locked`.
2. Read `package-lock.json` for npm build/test packages.
3. Read `requirements.txt`, `docs/requirements-mcp.txt` and the desktop package
   workflow for Python/runtime packages.
4. Review the classification of each entry and reconcile it against the
   actual release. Update `ip-inventory.json` and recompute its UTF-8 LF SHA-256.
   This is a review procedure, not a byte-for-byte inventory generator.
