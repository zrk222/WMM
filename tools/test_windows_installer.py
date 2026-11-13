"""Opt-in isolated Windows CI installer lifecycle; never installs prerequisites."""

import asyncio
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL_TIMEOUT_SECONDS = 180


def run(argv, cwd, env, timeout=INSTALL_TIMEOUT_SECONDS):
    return subprocess.run(
        [str(x) for x in argv], cwd=cwd, env=env, check=True, capture_output=True, text=True, timeout=timeout
    )


def verify_publisher(path, thumbprint, cwd, env):
    """Check Windows trust, the pinned publisher, and the timestamp on exact bytes."""
    command = (
        "$ErrorActionPreference='Stop'; "
        "$s=Get-AuthenticodeSignature -LiteralPath $env:WMM_CHECK_BINARY; "
        "if ($s.Status -ne 'Valid' -or "
        "$s.SignerCertificate.Thumbprint -cne $env:WMM_WINDOWS_SIGNER_THUMBPRINT -or "
        "-not $s.TimeStamperCertificate) { throw 'Publisher or timestamp verification failed' }"
    )
    run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd,
        dict(env, WMM_CHECK_BINARY=str(path), WMM_WINDOWS_SIGNER_THUMBPRINT=thumbprint),
        30,
    )


def compiler(environ):
    base = environ.get("ProgramFiles(x86)")
    path = Path(base) / "Inno Setup 6" / "ISCC.exe" if base else None
    if path is None or not path.is_file():
        raise RuntimeError("Inno Setup 6 ISCC.exe is required on the isolated Windows runner")
    return path


def verify_binary(binary, folder, env, label):
    shell = binary.parent / "WMM-Mission-Control.exe"
    if not shell.is_file():
        raise AssertionError("Installed native Mission Control window is missing")
    verifier = ROOT / "tools/test_native_desktop_bundle.py"
    pair = json.loads(run([sys.executable, verifier, binary.parent], folder, env, 90).stdout)
    window = json.loads(run([sys.executable, verifier, binary.parent, "--windows-window"], folder, env, 90).stdout)
    if pair.get("status") != "PASS" or window.get("status") != "PASS" or window.get("exit_code") != 0:
        raise AssertionError("Installed native window verification failed")
    evidence = ROOT / ".factory/packaged-native-window" / label
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "evidence.json").write_text(
        json.dumps(dict(source_sha=env.get("GITHUB_SHA"), pair=pair, window=window)), encoding="utf-8"
    )
    for args in (["--check"], ["--self-test"], ["--vault-self-test"], ["--agent-cli", "catalog"]):
        value = json.loads(run([binary, *args], folder, env, 90).stdout)
        if (
            args == ["--check"]
            and Path(value["data_directory"]).resolve()
            != (Path(env["LOCALAPPDATA"]) / "Wize Marketing Machine").resolve()
        ):
            raise AssertionError("Installed binary selected an unexpected workspace directory")
        if args in (["--self-test"], ["--vault-self-test"]) and value.get("status") != "PASS":
            raise AssertionError("Installed binary self-test did not pass")
    spec = importlib.util.spec_from_file_location("wmm_bundle_smoke", ROOT / "tools/smoke_desktop_bundle.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Packaged smoke verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    asyncio.run(module.mcp_smoke(binary, str(folder)))
    module.setup_smoke(binary, folder, env, label=label)
    module.first_packet_smoke(binary, folder, env, label=label, profile_dir=env["LOCALAPPDATA"])


def wait_removed(install, timeout=30):
    """Allow the uninstaller helper to finish self-deletion; never remove its files."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            entries = list(install.iterdir())
        except FileNotFoundError:
            return
        if not entries:
            return
        if time.monotonic() >= deadline:
            remaining = ", ".join(sorted(p.name for p in entries)[:10])
            raise AssertionError("Uninstall left program entries: " + remaining)
        time.sleep(0.1)


def main():
    if sys.platform != "win32" or os.environ.get("CI") != "true" or os.environ.get("WMM_INSTALLER_TEST") != "1":
        raise RuntimeError("Installer lifecycle requires an explicitly enabled isolated Windows CI runner")
    iscc = compiler(os.environ)
    bundle = (ROOT / "dist/desktop/WMM").resolve()
    if not (bundle / "WMM.exe").is_file() or not (bundle / "Open WMM.vbs").is_file():
        raise RuntimeError("Build the Windows desktop bundle before running installer verification")
    with tempfile.TemporaryDirectory(prefix="wmm-installer-ci-") as temporary:
        temp = Path(temporary).resolve()
        install = temp / "program"
        output = temp / "output"
        data = temp / "user-data"
        output.mkdir()
        data.mkdir()
        workspace = data / "Wize Marketing Machine"
        workspace.mkdir()
        marker = workspace / "workspace-fixture.txt"
        marker.write_text("synthetic private workspace", encoding="utf-8")
        env = dict(os.environ, LOCALAPPDATA=str(data))
        app_id = "WMM-CI-" + uuid.uuid4().hex
        script = ROOT / "packaging/windows/WMM.iss"
        release_installer = os.environ.get("WMM_RELEASE_INSTALLER")
        if release_installer:
            # The official AppId is safe only on a newly provisioned hosted runner.
            if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
                raise RuntimeError("Final installer acceptance requires a disposable GitHub-hosted runner")
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\WizeMarketingMachine_is1"
            try:
                existing = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)
            except FileNotFoundError:
                pass
            else:
                existing.Close()
                raise RuntimeError("Refusing a runner with an existing WMM installation")
            setup = Path(release_installer).resolve(strict=True)
        else:
            run(
                [
                    iscc,
                    "/DMyAppId=" + app_id,
                    "/DMyAppName=" + app_id,
                    "/DBundleDir=" + str(bundle),
                    "/DOutputDir=" + str(output),
                    script,
                ],
                temp,
                env,
            )
            setup = output / "WMM-Setup.exe"
        thumbprint = env.get("WMM_WINDOWS_SIGNER_THUMBPRINT")
        signature = {}
        installer_hash = None
        if thumbprint:
            if not re.fullmatch("[0-9A-F]{40}", thumbprint):
                raise ValueError("Expected an uppercase certificate thumbprint")
            with setup.open("rb") as stream:
                installer_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            verify_publisher(setup, thumbprint, temp, env)
        args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=" + str(install)]
        run([setup, *args], temp, env)
        binary = install / "WMM.exe"
        if not binary.is_file() or not (install / "Open WMM.vbs").is_file():
            raise AssertionError("Installed bundle is incomplete")
        verify_binary(binary, temp, env, "windows-fresh")
        run([setup, *args], temp, env)
        verify_binary(binary, temp, env, "windows-upgrade")
        if marker.read_text(encoding="utf-8") != "synthetic private workspace":
            raise AssertionError("Upgrade changed the workspace fixture")
        uninstaller = install / "unins000.exe"
        if thumbprint:
            verify_publisher(uninstaller, thumbprint, temp, env)
            with setup.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != installer_hash:
                    raise ValueError("Installer bytes changed during lifecycle verification")
            signature["publisher_signature"] = dict(
                thumbprint=thumbprint,
                installer_sha256=installer_hash,
                installer="VALID_TIMESTAMPED",
                uninstaller="VALID_TIMESTAMPED",
            )
        run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], temp, env)
        wait_removed(install)
        if binary.exists() or marker.read_text(encoding="utf-8") != "synthetic private workspace":
            raise AssertionError("Uninstall did not remove program or preserve workspace fixture")
    print(
        json.dumps(
            dict(
                status="PASS",
                install="VERIFIED",
                upgrade="VERIFIED",
                uninstall="VERIFIED",
                workspace="SYNTHETIC_PRESERVED",
                provider="NOT_RUN",
                **signature,
            )
        )
    )


if __name__ == "__main__":
    main()
