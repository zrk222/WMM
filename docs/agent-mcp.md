# WMM local MCP adapter

Use the [CLI/MCP quickstart](agent-quickstart.md) or
`python -m mission_control.agent_setup --origin http://127.0.0.1:8765`
to inspect dependencies and generate a scoped-grant configuration with the
actual interpreter and absolute module path.

Run from the WMM repository using Python with the optional SDK installed:

```powershell
python -m pip install -r docs/requirements-mcp.txt
python -m mission_control.agent_mcp --origin http://127.0.0.1:57599
```

The second command is a stdio server: an MCP host launches it and exchanges protocol messages over stdin/stdout. Start WMM separately. The optional requirements pin the tested official SDK baseline; they do not change the default WMM installation. Installation and registration never run automatically.

For a host supporting a standard `mcpServers` configuration, use your actual Python executable and repository path:

```json
{
  "mcpServers": {
    "wmm-local": {
      "command": "C:\\path\\to\\python.exe",
      "args": ["-m", "mission_control.agent_mcp", "--origin", "http://127.0.0.1:57599", "--use-grant"],
      "env": {"PYTHONPATH": "C:\\path\\to\\WMM"}
    }
  }
}
```

Hosts differ in configuration location and whether they accept `cwd`; set the process working directory or Python module search path to this repository using your host's supported settings. This document does not register or modify any host.

The generated example requires `WMM_AGENT_GRANT` in the host's protected process
environment. No token is included here. Hosts must support the shown environment
setting or an equivalent absolute module-search-path setting.

Call `wmm_catalog` with `{}` first. Current operation tools map dots to underscores: `growth.save` becomes `wmm_growth_save`. Supply the CLI envelope's `app_id`, `input` and, where required, `resource_id`; omit `operation` because the tool name fixes it. Required fields and exact outer schemas are advertised in tool discovery. Nested business values use the existing authoritative WMM validators. Reviewed-request tools are additionally advertised in grant mode; discover current tools instead of using a fixed historical count.

Example `wmm_growth_history` arguments:

```json
{"app_id":"demo-route-notes","input":{}}
```

Successful calls return `structuredContent.data` with the same JSON value returned by the CLI. Tool validation and business errors return MCP `isError: true`. Transport failures include a stable client error code. An interrupted write is unconfirmed: inspect saved history before deciding whether to retry. The adapter does not automatically retry writes. Each call uses its own in-memory cookie/CSRF session, exact loopback origin, redirect/proxy restrictions, byte limits and timeout from the shared client.

Discovery does not contact WMM. Read tools return private local workspace data. Connecting a model host shares the tool output with that host under its data settings. Use only an authorized host/account. Write annotations describe local evidence/plan effects; they are not independently enforced human approval. There are no identity login, credential, human approval, provider mutation, spending, publication, shell or arbitrary HTTP tools.

This adapter covers the fixed upgrade operation catalog. Owner-issued scoped grants and independent human checkpoint prepare/status/resume are available through the shared services. Launch with `--use-grant` to read the one-time credential from `WMM_AGENT_GRANT` in the adapter process environment; keep the credential out of prompts and reports. The grant enforces its current app, operations, expiry, revocation and call limits. Full-domain operation coverage and provider transports still require acceptance.

Protocol lifecycle and tool handling use the [official Python SDK 1.30.0](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0), following the MCP [stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) and [tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) contracts. Only stdio is enabled here; no additional network listener is created. This optional baseline passed real CLI/MCP conformance in a clean Python environment; installing it in your selected environment remains an explicit setup step.

The upstream [schema-resolution advisory](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-rwrf-2pqf-9j8j) and [HTTP-redirect advisory](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-5h93-6whr-6q8j) identify 1.30.0 as their patched 1.x release. Their affected paths concern SDK clients and HTTP transports. WMM exposes a stdio server, and its SDK clients run in controlled tests; these advisories do not establish an exploitable WMM path or a complete dependency audit.
