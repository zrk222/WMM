# IP component inventory

**Status: component/license evidence complete; ownership and agent terms review open.**
This is not a chain-of-title opinion, trademark clearance or commercial
relicensing permission.

Machine-readable inventory: [`ip-inventory.json`](ip-inventory.json)  
Inventory SHA-256: `e3665dd6ae728e2328c479c7be997e82d65b96596fc572a3c572415450c77e55`  
Components: **538** (418 Rust crates, 101 npm build/test packages, 8 Python/runtime
entries, 7 system/build entries, 3 first-party entries and 1 vendored JS library).

Release SBOM: [`wmm-release-sbom.cdx.json`](wmm-release-sbom.cdx.json) contains
the **434 shipped components** in CycloneDX 1.5 form and is bound to the current
main SHA and this inventory hash. The release workflow regenerates
`wmm-release-sbom-Windows.cdx.json` and `wmm-release-sbom-Linux.cdx.json` for the
exact candidate SHA. Checked-in SBOM SHA-256:
`fc3cbe092d657c9407caef1f37f684ef447ae52f8a67eedd4c947bfacb336a8c`.

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

## Per-file chain-of-title evidence

[`ip-file-ledger.json`](ip-file-ledger.json) records every one of the **1,982**
tracked files with first-add commit/date/author, last-change commit/date, authors,
license-boundary classification, distribution scope, explicit agent-assistance
flag and legal-assignment status.

- 168 files introduced under Apache-2.0.
- 151 Apache-introduced files later modified after the WMM license transition.
- 1,663 files introduced after the transition.
- Every row records `legal_assignment: OPEN`; Git authorship is evidence, not an
  assignment or a chain-of-title opinion.

Ledger SHA-256: `62364f82964b9370e97da671fd2e416f4a21bff2bb3685df00ee1645ac147976`

## Agent-assisted provenance

[`AGENT-PROVENANCE.md`](AGENT-PROVENANCE.md) records the evidence available in
the repository: author identities, the explicit `Instinct Agent` co-author
commit `e45b939`, agent `codex/*` branch evidence, current tool usage and missing
provider/tool-term retention. The absence of an agent trailer does not prove a
file was written without agent assistance.

## Resolved license questions

- **Icons:** introduced after the transition by `zrk222` in `15ff283`; no external
  source or embedded metadata found. Claimed first-party, subject to the global
  ownership review.
- **Ubuntu FFmpeg:** noble `7:6.1.1-3ubuntu5` default binary is GPL-2.0-or-later;
  libavcodec/libavfilter have a GPL-3+ flavor. It is an optional system
  dependency, not bundled.
- **WebKitGTK:** noble `2.52.6-0ubuntu0.24.04.1` is LGPL-2.1-or-later. It is a
  system dependency, dynamically linked, not bundled.
- **Inno Setup:** Inno Setup License permits commercial use and redistribution
  with notice conditions. Generated installers retain Inno notices. The exact
  runner-provided compiler version should be pinned.

## Open items

1. **Chain of title:** per-file Git evidence is recorded, but copyright
   assignment and contributor permission after the Apache-2.0 transition are not
   established. Counsel must review the ledger and obtain any missing assignment.
2. **Agent-assisted work:** repository evidence and current tool use are recorded,
   but provider/tool terms, full prompt logs and substantive human review records
   are not retained.
3. **Remotion:** confirm the applicable license for the rendered docs video.
4. **Exact release binding:** bind this inventory to the release candidate SBOM
   and shipped payload hashes. A build-environment SBOM alone is insufficient.
5. **Inno Setup version pin:** the license is reviewed, but the runner-provided
   compiler version is not pinned; record it in the release receipt.

## Reproduction

1. Generate Cargo metadata for both manifests with `--locked`.
2. Read `package-lock.json` for npm build/test packages.
3. Read `requirements.txt`, `docs/requirements-mcp.txt` and the desktop package
   workflow for Python/runtime packages.
4. Rebuild `ip-inventory.json`, recompute its SHA-256, and update the release
   clearance receipt only after human review.
