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
release and its logs explicitly before claiming successful distribution. This
workflow does not sign Windows binaries, install trust roots, bypass TLS, or prove
human first-use acceptance. The SBOM is a build-environment package inventory, not
a file-level runtime inventory or a provenance attestation. SHA256SUMS.txt covers
every uploaded asset.

## Installer checks

- Windows: per-user installer, no terminal or separate Python required.
- Ubuntu 24.04 amd64: graphical Debian package install, unlocked Secret Service
  keyring, browser available.
- Both: keep the desktop window open for its local engine; workspace data stays
  outside the installed program.

Unsigned Windows publisher verification and nontechnical first-use acceptance
remain separate evidence.

## Related

- [First-run guide](desktop-first-run.md)
- [Desktop runtime packages](../.github/workflows/desktop-packages.yml)
- [Desktop public prerelease](../.github/workflows/desktop-release.yml)
