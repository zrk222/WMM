"""Run the built executable from an unrelated directory, without installed source imports."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def public_signin_smoke(binary: Path, folder: str) -> dict[str, object]:
    """Check the frozen workspace without inheriting the build-time Client ID."""
    import runpy
    from urllib.request import urlopen

    expected = json.loads((ROOT / ".factory/desktop-config/public-config.json").read_text(encoding="utf-8"))
    environment = dict(os.environ)
    for key in ("WMM_GITHUB_DEVICE_CLIENT_ID", "PYTHONPATH", "WMM_AGENT_GRANT"):
        environment.pop(key, None)
    harness = runpy.run_path(str(ROOT / "tools/test_packaged_first_packet.py"))
    harness["preflight"](environment)
    with tempfile.TemporaryDirectory(prefix="wmm-public-signin-") as private:
        environment.update(LOCALAPPDATA=private, XDG_DATA_HOME=private, HOME=private, USERPROFILE=private)
        child = harness["_start"](binary, folder, environment)
        try:
            with urlopen(harness["ORIGIN"] + "/api/apps/sample-one", timeout=10) as response:  # noqa: S310 - fixed loopback fixture
                value = json.load(response)
            assert value["device_signin_available"] is bool(expected["github_device_client_id"]), (
                "Frozen sign-in readiness does not match the packaged public configuration"
            )
            assert value["identity"]["status"] == "SIGNED_OUT"
        finally:
            harness["_stop"](child)
    evidence: dict[str, object] = dict(
        status="PASS",
        device_signin_available=value["device_signin_available"],
        build_environment_removed=True,
        provider_access="NONE",
        source_sha=os.environ.get("GITHUB_SHA"),
    )
    print(json.dumps(dict(public_signin=evidence)))
    return evidence


def first_packet_smoke(binary, folder, env=None, label="runtime", profile_dir=None):
    """Exercise the frozen UI using the separate test-only browser harness."""
    import runpy

    harness = runpy.run_path(str(ROOT / "tools/test_packaged_first_packet.py"))
    evidence = harness["verify_frozen_first_packet"](binary, folder, env, label, profile_dir=profile_dir)
    print(json.dumps(dict(first_packet=evidence, phase=label)))
    return evidence


async def mcp_smoke(binary, folder, config=None, env=None):
    """Exercise the frozen stdio SDK lifecycle without a workspace or provider."""
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=config["command"] if config else str(binary),
        args=config["args"] if config else ["--mcp", "--origin", "http://127.0.0.1:1"],
        cwd=str(folder),
        env=env,
    )
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as diagnostics, anyio.fail_after(45):
        async with (
            stdio_client(params, errlog=diagnostics) as (reader, writer),
            ClientSession(reader, writer) as client,
        ):
            initialized = await client.initialize()
            assert initialized.serverInfo.name == "wmm-local-operations"
            tools = (await client.list_tools()).tools
            assert any(tool.name == "wmm_catalog" for tool in tools)
            assert len(tools) > 1
            await client.send_ping()
            result = await client.call_tool("wmm_catalog", {})
            assert not result.isError
            assert result.structuredContent is not None
            assert result.structuredContent["data"]["catalog_sha256"]
            failure = await client.call_tool("wmm_workspace_read", dict(app_id="sample-one", input={}))
            assert failure.isError
            assert failure.content[0].type == "text"
            assert "TRANSPORT_UNAVAILABLE" in failure.content[0].text
        diagnostics.seek(0)
        assert not diagnostics.read(1), "Healthy MCP session emitted stderr; shutdown was not clean"
    print(
        json.dumps(
            dict(
                command=["--mcp"],
                lifecycle="initialize-discover-ping-catalog-clean-close",
                workspace_access="UNAVAILABLE_AS_EXPECTED",
                provider_access="NONE",
            )
        )
    )


def setup_smoke(binary, folder, env=None, label="bundle"):
    """Use the installed setup output itself, with no repository/Python launch path."""
    binary = Path(binary).resolve()
    environment = dict(os.environ if env is None else env)
    environment.pop("WMM_AGENT_GRANT", None)
    environment.pop("PYTHONPATH", None)
    origin = "http://127.0.0.1:1"  # No live owner workspace or provider is contacted.
    result = subprocess.run(
        [str(binary), "--agent-setup", "--origin", origin, "--json"],
        cwd=folder,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    value = json.loads(result.stdout)
    assert value["runtime_kind"] == "PACKAGED_DESKTOP"
    assert value["origin"] == origin and value["server_status"] == "NOT_CHECKED_OFFLINE"
    assert value["cli"]["catalog"] == [str(binary), "--agent-cli", "catalog"]
    config = value["mcp_config"]["mcpServers"]["wmm-local"]
    assert config["command"] == str(binary)
    assert config["args"] == ["--mcp", "--origin", origin, "--use-grant"]
    assert not config.get("env")
    assert not value.get("repository") and not value.get("python")
    assert not value["mcp"].get("install")
    assert value["mcp"]["status"] == "DEPENDENCIES_AVAILABLE"
    catalog = subprocess.run(
        value["cli"]["catalog"], cwd=folder, env=environment, check=True, capture_output=True, text=True, timeout=90
    )
    assert json.loads(catalog.stdout)["catalog_sha256"]
    # The generated grant-required config fails before opening a transport when
    # its protected credential is absent. It must not fall back to browser authority.
    denied = subprocess.run(
        [config["command"], *config["args"]], cwd=folder, env=environment, capture_output=True, text=True, timeout=90
    )
    assert denied.returncode == 2 and not denied.stdout
    assert "requires WMM_AGENT_GRANT" in denied.stderr
    # A synthetic well-formed token permits protocol discovery, never access to
    # an actual account. Keep it in the child environment and out of receipts.
    import anyio

    anyio.run(mcp_smoke, binary, folder, config, dict(environment, WMM_AGENT_GRANT="wmmg_" + "s" * 43))
    evidence = dict(
        status="PASS",
        phase=label,
        runtime_kind=value["runtime_kind"],
        setup_command="--agent-setup",
        generated_cli_launched=True,
        generated_mcp_lifecycle=True,
        missing_grant_denied=True,
        repository_python_prerequisite=False,
        host_registered=False,
        provider_access="NONE",
        source_sha=os.environ.get("GITHUB_SHA"),
    )
    output = ROOT / ".factory/packaged-agent-setup-evidence"
    output.mkdir(parents=True, exist_ok=True)
    (output / (label + ".json")).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(dict(agent_setup=evidence)))
    return evidence


def main():
    binary = ROOT / "dist/desktop/WMM" / ("WMM.exe" if sys.platform == "win32" else "WMM")
    with tempfile.TemporaryDirectory() as folder:
        for arguments in (["--check"], ["--self-test"], ["--vault-self-test"], ["--agent-cli", "catalog"]):
            result = subprocess.run(
                [str(binary), *arguments], cwd=folder, check=True, capture_output=True, text=True, timeout=90
            )
            value = json.loads(result.stdout)
            if arguments in (["--self-test"], ["--vault-self-test"]):
                assert value["status"] == "PASS"
            if arguments == ["--self-test"]:
                tls = value["identity_tls"]
                assert tls["profile"] == ("WINDOWS_NATIVE_TRUSTSTORE" if sys.platform == "win32" else "STDLIB_DEFAULT")
                assert tls["context_constructed"] is True
                assert tls["certificate_required"] is True
                assert tls["check_hostname"] is True
                assert tls["minimum_tls_version"] == "TLSv1_2"
            print(json.dumps(dict(command=arguments, exit_code=result.returncode)))
        import anyio

        anyio.run(mcp_smoke, binary, folder)
        setup_smoke(binary, folder)
        public_signin_smoke(binary, folder)
        first_packet_smoke(binary, folder, label="bundle")


if __name__ == "__main__":
    main()
