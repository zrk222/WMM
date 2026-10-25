# Connect a local CLI or MCP host

Start WMM separately and keep it running. Open a terminal at the repository
root with the Python environment you intend to use. Replace port 8765 below
with the exact browser origin; only `http://127.0.0.1:PORT` is accepted.

```powershell
python -m mission_control.agent_cli --help
python -m mission_control.agent_cli catalog
python -m mission_control.agent_setup --origin http://127.0.0.1:8765
```

Setup is offline. It prints the actual interpreter and repository paths,
optional SDK availability and a reviewable MCP configuration. It does not
check server connectivity, issue a grant, read a token, install anything or
edit personal Codex/Claude settings. No `wmm` command is globally installed.

## Choose authority before connecting

- **Delegated agent:** in WMM, select the app, sign in under **Activity & reviews**
  as its OWNER, then open **Your agents → Manage agent grants**. Select only
  needed operations, expiry and call allowance. Keep independent write reviews
  enabled where required. Supply the once-only token as `WMM_AGENT_GRANT` using
  the host's protected process environment. Do not place it in a prompt,
  command argument, committed config or terminal history.
- **Trusted local session:** omitting `--use-grant` uses the existing local
  workstation session model. It is not a human sign-in, scoped delegation or
  checker approval. Protected operations may still reject it. The setup
  helper's generated MCP configuration always includes `--use-grant`.

For delegated CLI calls, first authorize `operations.read` in the grant, then
use the exact selected app ID:

```powershell
'{"app_id":"your-app-id","operation":"operations.read","input":{}}' | python -m mission_control.agent_cli call --origin http://127.0.0.1:8765 --use-grant
```

The credential must already be supplied securely in the process environment.
Missing, expired, revoked or insufficient grants fail without session fallback.
Catalog discovery is offline and does not prove permission. Use `operations.read`
to inspect selected-app policy and the current catalog for exact envelopes.

## Optional MCP

The CLI needs no MCP SDK. If setup reports missing optional dependencies,
review and run its installation command in the selected environment:

```powershell
python -m pip install -r docs/requirements-mcp.txt
python -m mission_control.agent_setup --origin http://127.0.0.1:8765 --json
```

The pinned tested SDK baseline is recorded in `docs/requirements-mcp.txt`.
Setup reports the installed version separately. A version mismatch is not proof
of protocol compatibility; use the pinned environment or run conformance checks.

Copy only the displayed `mcp_config` object into the configuration format your
authorized host supports, after review. Its absolute Python executable and
`PYTHONPATH` avoid depending on the host working directory. Preserve existing
host environment variables. Provide `WMM_AGENT_GRANT` through protected host
configuration; the generated JSON contains no token. Hosts differ in config
location and environment support, so no personal host registration is automatic.

The host launches `mission_control.agent_mcp` as a stdio process. It is not a
web address or a second HTTP service. Closing stdin ends that adapter process;
WMM continues separately. Call `wmm_catalog` first, then `wmm_operations_read`
with `{"app_id":"your-app-id","input":{}}`. Discover current tools rather than
relying on an old fixed count. Results contain private workspace data shared
with the selected host under its own data settings.

## Errors and next steps

`No module named mission_control` means the wrong working directory or module
path: use the repository root for CLI commands, or the generated absolute
`PYTHONPATH` configuration for the MCP host. Missing SDK errors name the optional
requirements file; no automatic installation occurs. A refused connection needs
the running WMM server and its exact origin. CLI errors use stderr; stdout stays
JSON. Never interpret an interrupted write as a confirmed failure or resubmit
automatically: inspect retained job/session history and UNKNOWN state first.

Use [CLI envelopes](agent-cli.md), [MCP protocol setup](agent-mcp.md),
[grant lifecycle](agent-grants.md) and [independent review transport](agent-review-transport.md)
for the respective contracts. Revoking a grant blocks future admissions; it
does not stop already-running work. Agents cannot approve their own checkpoint,
publish a campaign or spend through these adapters.
