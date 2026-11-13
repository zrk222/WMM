"""Fail-closed desktop prerelease protocol; no dependencies beyond Python and gh."""

import argparse
import hashlib
import json
import os
import re
import runpy
import subprocess
from pathlib import Path
from urllib.request import urlopen

ASSETS = {"Windows": "WMM-Setup.exe", "Linux": "wize-marketing-machine_0.1.0_amd64.deb"}
REPOSITORY = "zrk222/WMM"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_target(sha, main_sha, ref, repository, tag):
    if (
        not re.fullmatch("[0-9a-f]{40}", sha)
        or sha != main_sha
        or ref != "refs/heads/main"
        or repository != REPOSITORY
        or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?", tag)
    ):
        raise ValueError("Release requires official repository, main workflow, exact current main SHA and version tag")


def receipt(platform, sha, asset, lifecycle, destination, evidence_root=None):
    data = json.loads(Path(lifecycle).read_text(encoding="utf-8-sig").splitlines()[-1])
    removal = "uninstall" if platform == "Windows" else "removal"
    if (
        platform not in ASSETS
        or not re.fullmatch("[0-9a-f]{40}", sha)
        or data.get("status") != "PASS"
        or any(data.get(k) != "VERIFIED" for k in ("install", "upgrade", removal))
        or data.get("workspace") != "SYNTHETIC_PRESERVED"
    ):
        raise ValueError("Missing passing installer lifecycle result")
    asset = Path(asset)
    if asset.name != ASSETS[platform] or not asset.is_file() or asset.stat().st_size == 0:
        raise ValueError("Missing exact installer")
    evidence_root = (
        Path(evidence_root) if evidence_root else Path(__file__).resolve().parents[1] / ".factory/packaged-first-packet"
    )
    prefix = "windows" if platform == "Windows" else "ubuntu"
    offline = []
    for phase in ("fresh", "upgrade"):
        observed = json.loads((evidence_root / (prefix + "-" + phase) / "evidence.json").read_text())
        if (
            observed.get("github_sha") != sha
            or observed.get("offline_restart") != "PASS_SAME_PRIVATE_WORKSPACE_AND_BROWSER_STORAGE"
            or observed.get("network") != "BROWSER_EXTERNAL_BLOCKED_NOT_OS_OFFLINE"
        ):
            raise ValueError("Missing source-bound browser-isolated restart proof")
        offline.append(
            dict(
                phase=phase,
                evidence_sha256=digest(evidence_root / (prefix + "-" + phase) / "evidence.json"),
                offline_restart=observed["offline_restart"],
                network=observed["network"],
            )
        )
    Path(destination).write_text(
        json.dumps(
            dict(
                schema="wmm.desktop-release.v1",
                platform=platform,
                source_sha=sha,
                status="PASS",
                asset=asset.name,
                sha256=digest(asset),
                lifecycle=data,
                restart_checks=offline,
            ),
            indent=2,
        )
        + "\n"
    )


def validate_assets(folder, sha, require_provenance=False):
    folder = Path(folder)
    paths = [folder / name for name in ASSETS.values()]
    paths += [folder / ("sbom-" + platform + ".json") for platform in ASSETS]
    paths += [folder / (platform + ".json") for platform in ASSETS]
    evidence = [folder / name for name in ("release-attestation.sigstore.json", "release-provenance.json")]
    if require_provenance or any(path.exists() or path.is_symlink() for path in evidence):
        if not all(path.is_file() and not path.is_symlink() for path in evidence):
            raise ValueError("New releases require the complete downloadable provenance bundle and receipt")
        paths += evidence
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError("Release asset must be a nonempty regular file: " + path.name)
    manifest = folder / "SHA256SUMS.txt"
    if manifest.is_symlink() or (manifest.exists() and not manifest.is_file()):
        raise ValueError("Checksum manifest must be a regular file")
    manifest.write_text("".join(f"{digest(path)}  {path.name}\n" for path in paths), encoding="ascii")
    staged = paths + [manifest]
    verifier = runpy.run_path(str(Path(__file__).with_name("verify_release_assets.py")))
    verifier["verify_files"](staged, sha)
    return staged


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def validate_signing_config(thumbprint, timestamp_url):
    """Reject missing or malformed release settings before provisioning runners."""
    if not re.fullmatch("[0-9A-F]{40}", thumbprint or ""):
        raise ValueError("Configure WMM_WINDOWS_SIGNER_THUMBPRINT with the uppercase publisher thumbprint")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]+)?(?:/[A-Za-z0-9._/-]*)?", timestamp_url or ""):
        raise ValueError("Configure WMM_WINDOWS_TIMESTAMP_URL with the signer's HTTPS timestamp endpoint")


def require_windows_signature(folder, expected_thumbprint):
    """Require attested lifecycle evidence for the exact Windows release bytes."""
    if not re.fullmatch("[0-9A-F]{40}", expected_thumbprint or ""):
        raise ValueError("Configure the expected Windows publisher certificate thumbprint")
    folder = Path(folder)
    observation = json.loads((folder / "Windows.json").read_text(encoding="utf-8"))["lifecycle"].get(
        "publisher_signature"
    )
    installer_hash = digest(folder / ASSETS["Windows"])
    if observation != {
        "thumbprint": expected_thumbprint,
        "installer_sha256": installer_hash,
        "installer": "VALID_TIMESTAMPED",
        "uninstaller": "VALID_TIMESTAMPED",
    }:
        raise ValueError("Missing verified Windows installer and uninstaller publisher signatures")


def windows_release_notice(folder, tag):
    if os.environ.get("WMM_UNSIGNED_WINDOWS_PREVIEW10") == "true":
        if tag != "v0.1.0-preview.10":
            raise ValueError("Unsigned Windows publication is limited to Preview 10")
        lifecycle = json.loads((Path(folder) / "Windows.json").read_text(encoding="utf-8"))["lifecycle"]
        if lifecycle.get("publisher_signature") is not None:
            raise ValueError("Expected an unsigned Windows lifecycle receipt")
        return "The Windows installer is unsigned. SmartScreen may warn or block installation. "
    require_windows_signature(folder, os.environ.get("WMM_WINDOWS_SIGNER_THUMBPRINT"))
    return "Windows installer and uninstaller publisher signatures were verified during lifecycle testing. "


def publish(folder, sha, tag):
    repo = json.loads(gh("api", "repos/" + REPOSITORY))
    main = gh("api", "repos/" + REPOSITORY + "/git/ref/heads/main", "--jq", ".object.sha").strip()
    validate_target(sha, main, os.environ.get("GITHUB_REF"), os.environ.get("GITHUB_REPOSITORY"), tag)
    if repo.get("private") is not False:
        raise ValueError("Anonymous installer downloads require a public repository")
    paths = validate_assets(folder, sha, require_provenance=True)
    windows_notice = windows_release_notice(folder, tag)
    # A successful list proves absence. API/network errors abort rather than looking like 404.
    refs = json.loads(gh("api", "repos/" + REPOSITORY + "/git/matching-refs/tags/" + tag))
    releases = json.loads(gh("api", "--paginate", "--slurp", "repos/" + REPOSITORY + "/releases"))
    if any(r["ref"] == "refs/tags/" + tag for r in refs) or any(
        r["tag_name"] == tag for page in releases for r in page
    ):
        raise ValueError("Existing release/tag is immutable; choose a new version")
    notes = (
        "Windows and Ubuntu amd64 preview installers. No system Python required. "
        "SHA256SUMS.txt covers the eight other release assets. sbom-Windows.json and sbom-Linux.json list the "
        "build-environment packages; this is not a runtime file inventory. "
        "release-attestation.sigstore.json contains the GitHub provenance bundle for the six payloads; "
        "release-provenance.json retains the source-bound verification results. "
        "Neither the checksum manifest nor the provenance receipt is itself attested. "
        + windows_notice
        + "See docs/desktop-first-run.md at source commit " + sha + ". "
        "Automated synthetic installer checks are not human first-use acceptance."
    )
    gh(
        "release",
        "create",
        tag,
        "--repo",
        REPOSITORY,
        "--target",
        sha,
        "--draft",
        "--prerelease",
        "--title",
        "WMM Desktop " + tag,
        "--notes",
        notes,
    )
    # Never --clobber. Failure leaves a draft for inspection and cannot overwrite assets on retry.
    gh("release", "upload", tag, "--repo", REPOSITORY, *map(str, paths))
    uploaded = json.loads(
        gh("release", "view", tag, "--repo", REPOSITORY, "--json", "assets,isDraft,isPrerelease,targetCommitish")
    )
    expected = {p.name: p.stat().st_size for p in paths}
    if (
        not uploaded.get("isDraft")
        or not uploaded.get("isPrerelease")
        or uploaded.get("targetCommitish") != sha
        or {a["name"]: a["size"] for a in uploaded["assets"]} != expected
    ):
        raise ValueError("Draft asset readback mismatch; draft preserved")
    gh("release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--prerelease")
    actual = gh("api", "repos/" + REPOSITORY + "/git/ref/tags/" + tag, "--jq", ".object.sha").strip()
    if actual != sha:
        raise ValueError("Published tag does not point to the tested commit")
    # Native HTTPS validation, anonymous full-byte download: no token, custom CA or TLS bypass.
    for path in paths:
        url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{path.name}"
        with urlopen(url, timeout=120) as response:  # noqa: S310 - fixed HTTPS origin; validated tag and asset names
            downloaded = hashlib.file_digest(response, "sha256").hexdigest()
        if downloaded != digest(path):
            raise ValueError("Public download hash mismatch: " + url)
    print(
        json.dumps(
            dict(
                status="PASS",
                source_sha=sha,
                tag=tag,
                url=f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
                anonymous_downloads_verified=True,
            )
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("receipt")
    for name in ("platform", "sha", "asset", "lifecycle", "destination"):
        record.add_argument("--" + name, required=True)
    release = sub.add_parser("publish")
    for name in ("folder", "sha", "tag"):
        release.add_argument("--" + name, required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    (receipt if command == "receipt" else publish)(**args)


if __name__ == "__main__":
    main()
