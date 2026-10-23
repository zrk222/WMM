# WMM local MCP adapter

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
      "args": ["-m", "mission_control.agent_mcp", "--origin", "http://127.0.0.1:57599"],
      "cwd": "C:\\path\\to\\WMM"
    }
  }
}
```

Hosts differ in configuration location and whether they accept `cwd`; set the process working directory or Python module search path to this repository using your host's supported settings. This document does not register or modify any host.

Call `wmm_catalog` with `{}` first. The other fifteen tools map dots to underscores: `growth.save` becomes `wmm_growth_save`. Supply the CLI envelope's `app_id`, `input` and, where required, `resource_id`; omit `operation` because the tool name fixes it. Required fields and exact outer schemas are advertised in tool discovery. Nested business values use the existing authoritative WMM validators.

Example `wmm_growth_history` arguments:

```json
{"app_id":"demo-route-notes","input":{}}
```

Successful calls return `structuredContent.data` with the same JSON value returned by the CLI. Tool validation and business errors return MCP `isError: true`. Transport failures include a stable client error code. An interrupted write is unconfirmed: inspect saved history before deciding whether to retry. The adapter does not automatically retry writes. Each call uses its own in-memory cookie/CSRF session, exact loopback origin, redirect/proxy restrictions, byte limits and timeout from the shared client.

Discovery does not contact WMM. Read tools return private local workspace data. Connecting a model host shares the tool output with that host under its data settings. Use only an authorized host/account. Write annotations describe local evidence/plan effects; they are not independently enforced human approval. There are no identity login, credential, human approval, provider mutation, spending, publication, shell or arbitrary HTTP tools.

This adapter covers the fixed upgrade operation catalog. Full-domain operation schemas, authenticated scoped agent grants, independent human checkpoint dispatch/resume, provider transports and their acceptance remain required. It does not establish full autonomous WMM operation.

Protocol lifecycle and tool handling use the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.16.0), following the MCP [stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) and [tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) contracts. Only stdio is enabled here; no additional network listener is created.
