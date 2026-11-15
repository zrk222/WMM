# Release handoff (maintainers)

This guide moves installer publishing out of the buyer-facing first-run guide.
It does not change the release checks; it only records where they live.

## Publish a desktop preview

Merge the reviewed candidate into main. Use **Desktop runtime packages** for a
build-only hosted check. After reviewing that evidence and obtaining explicit
approval to publish, dispatch **Desktop public prerelease** from main with the
exact current main commit SHA and a new version tag such as
`v0.1.0-preview.1`. The workflow reruns the Windows and Ubuntu installer checks,
records the tested installer hashes, and publishes only when both jobs pass.
Only the final publication job receives repository contents write permission.
Pull requests cannot trigger publication.

The publisher creates a draft prerelease, uploads the two native installers,
their source-bound lifecycle receipts, one build-environment SBOM per platform
(`sbom-Windows.json`, `sbom-Linux.json`) and SHA256SUMS.txt, checks the draft
asset names/sizes, then publishes. It downloads the public assets anonymously over
normal verified HTTPS and compares full SHA256 hashes. Retain the successful run
URL and publisher readback as release evidence. CI logs and source archives alone
are not installer distribution proof.

Existing tags/releases/assets are never overwritten. An interrupted upload leaves
a draft for inspection; choose a new tag after resolving the cause. A
public-download verification failure may occur after publication: inspect that
release and its logs explicitly before claiming successful distribution. The public workflow requires a trusted Windows signing provider available to the
Windows runner. Configure the public certificate thumbprint (uppercase) as
`WMM_WINDOWS_SIGNER_THUMBPRINT` and its HTTPS timestamp endpoint as
`WMM_WINDOWS_TIMESTAMP_URL`. These settings do not provision a key or certificate.
The installer and installed uninstaller must pass Windows signature verification
under that identity before the release can publish. Build-only runs stay unsigned.
Signing does not install trust roots, bypass TLS, or prove human first-use acceptance. The SBOM is a build-environment package inventory, not
a file-level runtime inventory or a provenance attestation. SHA256SUMS.txt covers
the eight other release assets.

Before the publisher creates SHA256SUMS.txt, the pinned GitHub attestation action
attests the exact six staged payloads. `tools/verify_release_provenance.py` then
requires the official `gh attestation verify` result for each payload, constrained
to repository `zrk222/WMM`, signer workflow
`zrk222/WMM/.github/workflows/desktop-release.yml`, the exact admitted source SHA,
and GitHub-hosted runners. Missing or failed results stop publication. The helper
rejects missing, empty, linked or extra stage entries and changed bytes during
verification, then writes `.factory/release-provenance.json` outside the release
folder. That receipt must upload successfully before the immutable publisher
runs. After all six payload verifications pass, the exact action-generated bundle is copied as `release-attestation.sigstore.json`, and the complete source-bound verification receipt as `release-provenance.json`. Both are explicit public release assets covered by the checksum manifest. They are not added to the six attestation subjects, and no recursive checksum or receipt attestation is claimed.

The receipt records payload hashes, bundle hash, verifier result counts, full verifier outputs and their hashes;
it is execution evidence, not a substitute for independently verifying downloaded
payloads with the [buyer verification commands](VERIFY-RELEASE.md). The checksum
manifest is created later, covers all eight other assets and is not itself attested. Provenance verification does not substitute for Windows publisher verification.

## Installer checks

- Windows: per-user installer, no terminal or separate Python required.
- Ubuntu 24.04 amd64: graphical Debian package install, unlocked Secret Service
  keyring, browser available.
- Both: keep the desktop window open for its local engine; workspace data stays
  outside the installed program.

Publisher verification and nontechnical first-use acceptance remain separate evidence.

## Related

- [First-run guide](desktop-first-run.md)
- [Desktop runtime packages](../.github/workflows/desktop-packages.yml)
- [Desktop public prerelease](../.github/workflows/desktop-release.yml)
