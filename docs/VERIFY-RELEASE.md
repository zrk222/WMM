# Verify a downloaded preview release

Use the release's own checksum manifest; do not fetch hashes from a chat, issue or mirror.

```sh
python tools/verify_release_assets.py --folder ./WMM-preview --source-sha <exact 40-hex source>
```

Use this verifier for releases that include both SBOMs and a checksum manifest covering all six payload files. Preview 7 and earlier have the older installer-only checksum format. Keep those releases intact and use their own checksum manifests to verify the installer bytes.

Download into one folder:

- `WMM-Setup.exe`
- `wize-marketing-machine_0.1.0_amd64.deb`
- `Windows.json`, `Linux.json`
- `sbom-Windows.json`, `sbom-Linux.json`
- `SHA256SUMS.txt`

The verifier fails if:

- the manifest is empty, malformed, duplicated or incomplete;
- any listed file is missing, has changed bytes, is a symlink or has an extra unlisted file;
- an installer receipt does not match the platform, asset name, source SHA, installer hash or passing lifecycle evidence;
- an SBOM is not CycloneDX 1.5, is not bound to the requested source SHA, or is not labeled `build_environment`;
- the downloaded folder contains an unexpected file.

It prints a JSON `PASS` only after every check. This verifies downloaded bytes and metadata; it does not prove code signing, reproducible builds, provider behavior or human first use.
