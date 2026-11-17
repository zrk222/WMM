"""Offline discovery and an explicit, scoped owner-host connection check."""

import argparse
import json
import sys
from importlib import metadata, util
from pathlib import Path
from typing import NotRequired, TypedDict

from .common import Invalid
from .operation_catalog import request_data
from .operator_client import ClientError, OperatorClient, grant_environment, origin_data

VERIFY_STEP = (
    "Run the owner-host verification command with your app ID and an injected WMM_AGENT_GRANT. "
    "It consumes one admitted read attempt. Cloud-only hosts need a separately supported connection."
)


class VerificationCommand(TypedDict):
    command: list[str]
    operation: str
    server_status: str
    authorization: str
    cloud_only: str


class Dependency(TypedDict):
    module: str
    status: str
    version: str | None


class MCPStatus(TypedDict):
    status: str
    tested_sdk_baseline: str
    matches_tested_baseline: bool
    dependencies: list[Dependency]
    install: NotRequired[list[str]]


class MCPLaunch(TypedDict):
    command: str
    args: list[str]
    env: dict[str, str]


class CLIStatus(TypedDict):
    status: str
    catalog: list[str]


class SetupReport(TypedDict):
    schema: str
    runtime_kind: str
    python: str | None
    repository: str | None
    origin: str
    server_status: str
    python_supported: bool | None
    cli: CLIStatus
    owner_host_verification: VerificationCommand
    mcp: MCPStatus
    mcp_config: dict[str, dict[str, MCPLaunch]]
    authority: str
    next_steps: list[str]


def verification_command(launch: list[str], origin: str, app_id: str | None = None) -> VerificationCommand:
    return VerificationCommand(
        command=[*launch, "--origin", origin, "--verify-app", app_id if app_id is not None else "<app-id>", "--json"],
        operation="operations.read",
        server_status="NOT_CHECKED_OFFLINE",
        authorization="INJECTED_WMM_AGENT_GRANT_ONLY",
        cloud_only="REQUIRES_SEPARATE_SUPPORTED_CONNECTION",
    )


def verified_receipt(value: object, app_id: str) -> dict[str, object]:
    """Allow only selected shape-checked facts to leave scoped discovery."""
    if not isinstance(value, dict) or value.get("schema") != "growth.agent-operations.v1":
        raise ClientError("INVALID_RESPONSE", "The local server did not return WMM operation discovery.")
    if value.get("app_id") != app_id or value.get("transport") != "LOOPBACK_HTTP_JSON":
        raise ClientError("INVALID_RESPONSE", "The local server did not confirm the requested app and transport.")
    version = value.get("manifest_version")
    authority = value.get("agent_authority")
    if type(version) is not int or version < 1 or not isinstance(authority, dict):
        raise ClientError("INVALID_RESPONSE", "The local server did not confirm scoped admission.")
    remaining = authority.get("remaining_calls")
    if type(remaining) is not int or remaining < 0:
        raise ClientError("INVALID_RESPONSE", "The local server did not confirm the grant allowance.")
    return dict(manifest_version=version, remaining_calls=remaining)


def verify_owner_host(origin: str, app_id: str, *, packaged: bool = False) -> dict[str, object]:
    """Perform one exact app policy read with the host's injected grant only."""
    origin_data(origin)
    envelope = dict(app_id=app_id, operation="operations.read", input={})
    request_data(envelope)
    token = grant_environment(True)
    if token is None:
        raise Invalid("Inject WMM_AGENT_GRANT on the owner host before verifying")
    result = OperatorClient(origin, grant_token=token).call(envelope)
    return dict(
        schema="wmm.owner-host-verification.v1",
        status="VERIFIED_OWNER_HOST_ACCESS",
        runtime_kind="PACKAGED_DESKTOP" if packaged else "SOURCE_PYTHON",
        tool="AGENT_SETUP_CLI",
        transport="SCOPED_LOOPBACK_HTTP_JSON",
        origin=origin,
        app_id=app_id,
        operation="operations.read",
        **verified_receipt(result, app_id),
        remote_mcp_verified=False,
        provider_read=False,
        external_write=False,
    )


def verification_error(error: ClientError) -> dict[str, object]:
    messages = {
        "TRANSPORT_UNAVAILABLE": "Start WMM on this owner host and verify the exact loopback port.",
        "GRANT_REJECTED": "Ask the WMM app owner to check the grant's app, expiry, allowance and operations.read scope.",
        "INVALID_RESPONSE": "Check that the exact loopback port runs the expected WMM installation.",
        "REDIRECT_REJECTED": "Use the exact local WMM port. No redirect was followed.",
    }
    code = "GRANT_REJECTED" if error.status == 403 else error.code
    if code not in messages:
        code = "INVALID_RESPONSE"
    return dict(code=code, message=messages[code])


def dependency(name: str) -> Dependency:
    """Inspect availability without importing the optional adapter or SDK."""
    if util.find_spec(name) is None:
        return Dependency(module=name, status="MISSING", version=None)
    try:
        version = metadata.version(name)
    except metadata.PackageNotFoundError:
        version = None
    return Dependency(module=name, status="AVAILABLE", version=version)


def report(origin: str, *, runtime_executable: str | Path | None = None, app_id: str | None = None) -> SetupReport:
    """Emit setup facts for source Python or a frozen desktop executable."""
    origin_data(origin)
    if runtime_executable is not None:
        executable = str(Path(runtime_executable).resolve())
        deps = [dependency(name) for name in ("mcp", "anyio")]
        ready = all(d["status"] == "AVAILABLE" for d in deps)
        baseline = deps[0]["version"] == "1.30.0"
        return SetupReport(
            schema="wmm.agent-setup.v1",
            runtime_kind="PACKAGED_DESKTOP",
            python=None,
            repository=None,
            origin=origin,
            server_status="NOT_CHECKED_OFFLINE",
            python_supported=None,
            cli=CLIStatus(status="AVAILABLE", catalog=[executable, "--agent-cli", "catalog"]),
            owner_host_verification=verification_command([executable, "--agent-setup"], origin, app_id),
            mcp=MCPStatus(
                status="DEPENDENCIES_AVAILABLE" if ready else "OPTIONAL_DEPENDENCIES_MISSING",
                tested_sdk_baseline="1.30.0",
                matches_tested_baseline=baseline,
                dependencies=deps,
            ),
            mcp_config=dict(
                mcpServers={
                    "wmm-local": MCPLaunch(
                        command=executable, args=["--mcp", "--origin", origin, "--use-grant"], env={}
                    )
                }
            ),
            authority="OWNER_ISSUED_SCOPED_GRANT_REQUIRED_FOR_GENERATED_CONFIG",
            next_steps=[
                "Start WMM separately at the exact origin shown; offline discovery does not verify a running server.",
                "For delegated access, sign in under Activity & reviews as this app OWNER, then Manage agent grants.",
                "Supply WMM_AGENT_GRANT using the host protected process environment; no token belongs in configuration examples or prompts.",
                "Review and register the displayed MCP configuration manually in an authorized host. This command changes no host settings.",
                "Call wmm_catalog to discover current tools, then operations.read for selected-app policy. Missing grant never falls back to session authority.",
                VERIFY_STEP,
            ],
        )
    root = Path(__file__).resolve().parent.parent
    python = str(Path(sys.executable).resolve())
    deps = [dependency(name) for name in ("mcp", "anyio")]
    ready = all(d["status"] == "AVAILABLE" for d in deps)
    baseline = deps[0]["version"] == "1.30.0"
    return SetupReport(
        schema="wmm.agent-setup.v1",
        runtime_kind="SOURCE_PYTHON",
        python=python,
        repository=str(root),
        origin=origin,
        server_status="NOT_CHECKED_OFFLINE",
        python_supported=sys.version_info >= (3, 11),
        cli=CLIStatus(status="AVAILABLE", catalog=[python, "-m", "mission_control.agent_cli", "catalog"]),
        owner_host_verification=verification_command([python, "-m", "mission_control.agent_setup"], origin, app_id),
        mcp=MCPStatus(
            status="DEPENDENCIES_AVAILABLE" if ready else "OPTIONAL_DEPENDENCIES_MISSING",
            tested_sdk_baseline="1.30.0",
            matches_tested_baseline=baseline,
            dependencies=deps,
            install=[python, "-m", "pip", "install", "-r", str(root / "docs" / "requirements-mcp.txt")],
        ),
        mcp_config=dict(
            mcpServers={
                "wmm-local": MCPLaunch(
                    command=python,
                    args=["-m", "mission_control.agent_mcp", "--origin", origin, "--use-grant"],
                    env=dict(PYTHONPATH=str(root)),
                )
            }
        ),
        authority="OWNER_ISSUED_SCOPED_GRANT_REQUIRED_FOR_GENERATED_CONFIG",
        next_steps=[
            "Start WMM separately at the exact origin shown; offline discovery does not verify a running server.",
            "For delegated access, sign in under Activity & reviews as this app OWNER, then Manage agent grants.",
            "Supply WMM_AGENT_GRANT using the host protected process environment; no token belongs in configuration examples or prompts.",
            "Review and register the displayed MCP configuration manually in an authorized host. This command changes no host settings.",
            "Call wmm_catalog to discover current tools, then operations.read for selected-app policy. Missing grant never falls back to session authority.",
            VERIFY_STEP,
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect local CLI/MCP setup offline, or opt in to one scoped owner-host verification read. No install or registration."
    )
    parser.add_argument("--origin", required=True, help="Exact running WMM origin, e.g. http://127.0.0.1:8765")
    parser.add_argument("--json", action="store_true", help="Print machine-readable setup facts and configuration")
    parser.add_argument(
        "--verify-app", metavar="APP_ID", help="Opt in to one scoped read using injected WMM_AGENT_GRANT"
    )
    args = parser.parse_args(argv)
    packaged = bool(getattr(sys, "frozen", False))
    try:
        if args.verify_app is not None:
            print(json.dumps(verify_owner_host(args.origin, args.verify_app, packaged=packaged), indent=2))
            return 0
        value = report(args.origin, runtime_executable=sys.executable if packaged else None)
    except Invalid as error:
        print(json.dumps(dict(error=str(error))), file=sys.stderr)
        return 2
    except ClientError as error:
        print(json.dumps(dict(status="OWNER_HOST_ACCESS_UNVERIFIED", error=verification_error(error))), file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(value, indent=2))
    else:
        if value["runtime_kind"] == "PACKAGED_DESKTOP":
            print("Desktop executable: " + value["cli"]["catalog"][0])
        else:
            print(f"Python: {value['python']}")
            print(f"Repository: {value['repository']}")
        print("WMM: " + value["origin"] + " (not contacted)")
        print("CLI: " + " ".join(value["cli"]["catalog"]))
        print("MCP: " + value["mcp"]["status"])
        print("Tested SDK baseline matches: " + str(value["mcp"]["matches_tested_baseline"]))
        if "install" in value["mcp"]:
            print("Optional installation command: " + " ".join('"' + a + '"' for a in value["mcp"]["install"]))
        print(json.dumps(value["mcp_config"], indent=2))
        print(json.dumps(value["owner_host_verification"]["command"]))
        for step in value["next_steps"]:
            print(step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
