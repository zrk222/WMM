# IP component inventory

**Status: component inventory complete; ownership and relicensing review open.**
This is not a chain-of-title opinion, trademark clearance or commercial
relicensing permission.

Machine-readable inventory: [`ip-inventory.json`](ip-inventory.json)  
Inventory SHA-256: `dbfacd34bcedfb0c498e6c2354bbe027abdd2b2e27846ad75930a5c640c994cc`  
Components: **538** (418 Rust crates, 101 npm build/test packages, 8 Python/runtime
entries, 7 system/build entries, 3 first-party entries and 1 vendored JS library).

## Shipment model

The desktop payload contains:

- WMM Python source, static assets and migrations, compiled by PyInstaller.
- CPython 3.11 plus PyInstaller, tzdata, truststore and platform storage packages.
- On Linux, system packages including WebKitGTK 4.1, DejaVu fonts and optional
  FFmpeg.
- On Windows, the system Microsoft Edge WebView2 Runtime and the Tauri launcher.
- Rust crates from `desktop/src-tauri/Cargo.lock` and
  `desktop/launcher/Cargo.lock`.
- The vendored Three.js bundle used by the public overview page.
- Synthetic screenshots and a Remotion-rendered preview video.

npm packages in `package-lock.json` are build/test tooling and are marked
`shipped: false`. Inno Setup, Playwright and Remotion are build or documentation
tools, not part of the desktop payload.

## Shipped license families

| Family | Count |
| --- | ---: |
| MIT | 303 |
| Apache-2.0 | 37 |
| Zlib | 19 |
| Unicode-3.0 | 18 |
| MIT/Apache-2.0 variants | 22 |
| Unlicense / MIT / 0BSD | 12 |
| BSD-3-Clause variants | 8 |
| MPL-2.0 | 5 |
| PSF-2.0 | 1 |
| LGPL-2.1-or-later (WebKitGTK) | 1 |
| GPL-2.0-or-later (FFmpeg build-dependent) | 1 |
| Microsoft WebView2 terms | 1 |
| First-party WMM license/asset claims | 3 |
| Bitstream Vera / DejaVu | 1 |

Review the exact machine inventory for every component, version, source and
evidence path. The largest obligation clusters are MPL-2.0 file-level copyleft,
LGPL WebKitGTK dynamic linking, build-dependent FFmpeg terms, and the
PyInstaller bootloader exception.

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

## Reproduction

1. Generate Cargo metadata for both manifests with `--locked`.
2. Read `package-lock.json` for npm build/test packages.
3. Read `requirements.txt`, `docs/requirements-mcp.txt` and the desktop package
   workflow for Python/runtime packages.
4. Rebuild `ip-inventory.json`, recompute its SHA-256, and update the release
   clearance receipt only after human review.
