"""Detected installed REA and bounded shell-free native process execution."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import tomllib
from .common import Invalid, digest

MAX_OUTPUT = 8388608
ECC_NAMES = ("click-path-audit", "loop-design-check")


def file_hash(path):
    """Hash executable and instruction bytes without loading binaries into memory."""
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def installed(home):
    """Use the existing exact REA registration, never install or accept client commands."""
    config = tomllib.loads((home / ".codex/config.toml").read_text(encoding="utf-8"))
    entry = config["mcp_servers"]["rea"]
    node = Path(entry["command"]).resolve()
    args = entry["args"]
    if len(args) != 2 or args[1] != "mcp":
        raise Invalid("REA registration uses an unsupported launch contract")
    script = Path(args[0]).resolve()
    package = script.parent.parent
    identity = json.loads((package / "package.json").read_text(encoding="utf-8"))
    if node.name not in ("node.exe", "node") or script.name != "rea.mjs" or script.parent.name != "scripts":
        raise Invalid("Select the existing native REA Node registration")
    if identity.get("name") != "rea-agents" or identity.get("version") != "6.4.0":
        raise Invalid("This adapter supports the installed rea-agents 6.4.0 contract")
    browsers = sorted((home / "AppData/Local/ms-playwright").glob("chromium-*/chrome-win64/chrome.exe"))
    if not browsers:
        raise Invalid("No installed Playwright Chromium found")
    return node, script, browsers[-1].resolve()


def skills(home):
    """Bind the direct rule-review mode to both installed ECC instruction files."""
    result = {}
    for name in ECC_NAMES:
        matches = sorted((home / ".codex/plugins/cache/ecc/ecc").glob("*/skills/" + name + "/SKILL.md"))
        if not matches:
            raise Invalid("Install the ECC plugin before enabling skill review")
        path = matches[-1].resolve()
        result[name] = {"path": str(path), "sha256": file_hash(path)}
    return result


def capability(home=None):
    """Return a detected fingerprint or actionable unavailable state, without executing tools."""
    try:
        home = Path(home) if home else Path.home()
        node, script, browser = installed(home)
        result = {"status": "READY", "node": str(node), "script": str(script), "browser": str(browser),
                  "version": "6.4.0", "skills": skills(home)}
        result["hashes"] = {str(p): file_hash(p) for p in (node, script, browser)}
        result["package_sha256"] = package_hash(script.parent.parent)
        result["id"] = digest(result)
        return result
    except (OSError, KeyError, TypeError, ValueError, Invalid):
        return {"status": "BLOCKED", "id": None,
                "repair": "Use the existing REA 6.4.0 Codex registration, installed Playwright Chromium and ECC plugin. No installation or credentials are performed here."}


def package_hash(package):
    """Bind REA entrypoint imports as well as the launch script, without acquiring code."""
    files=[package/"package.json"]
    for folder in ("dist","scripts"):
        files.extend(p for p in (package/folder).rglob("*") if p.is_file())
    return digest({str(p.relative_to(package)):file_hash(p) for p in sorted(files)})


def restricted_environment():
    """Exclude inherited tokens, provider keys and personal browser profile configuration."""
    allowed = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LOCALAPPDATA", "USERPROFILE", "PATH")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def stop_owned(process):
    """Terminate the still-owned process tree, never a name-matched unrelated process."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        taskkill = str(Path(os.environ["SYSTEMROOT"]) / "System32/taskkill.exe")
        subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                       creationflags=subprocess.CREATE_NO_WINDOW, shell=False)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=15)


def await_process(process, output, error, alive, timeout):
    """Bound time, cancellation and disk output before interpreting any native response."""
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        alive()
        if time.monotonic() > deadline:
            raise Invalid("Inspection timed out; review its steps before an explicit rerun")
        if output.stat().st_size + error.stat().st_size > MAX_OUTPUT:
            raise Invalid("Inspection output exceeded its bounded evidence size")
        time.sleep(0.1)
    alive()
    if output.stat().st_size + error.stat().st_size > MAX_OUTPUT:
        raise Invalid("Inspection output exceeded its bounded evidence size")


def invoke(tools, scenario, alive, timeout=90):
    """Capture one frozen scenario in an owned temporary directory with fixed CLI arguments."""
    with tempfile.TemporaryDirectory(prefix="growth-rea-owned-") as name:
        folder = Path(name)
        request = folder / "scenario.json"
        request.write_text(json.dumps(scenario), encoding="utf-8")
        output, error = folder / "evidence.json", folder / "error.txt"
        args = [tools["node"], tools["script"], "capture-browser-scenario", str(request),
                "--format", "json", "--full-output"]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with output.open("wb") as stdout, error.open("wb") as stderr:
            process = subprocess.Popen(args, cwd=folder, env=restricted_environment(), stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, shell=False, creationflags=flags,
                                       start_new_session=os.name != "nt")
            try:
                await_process(process, output, error, alive, timeout)
                code = process.returncode
            finally:
                stop_owned(process)
        if code:
            raise Invalid("REA native process failed; inspect installation and declared steps before rerun")
        try:
            value = json.loads(output.read_bytes())
        except (ValueError, UnicodeError) as exc:
            raise Invalid("REA returned invalid evidence; execution was not accepted") from exc
        return value
