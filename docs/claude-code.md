# Connect Claude Code to Wize Marketing Machine

Use Claude Code on the computer running WMM. Start WMM first and keep it open.
This connects an existing installation; it does not install WMM or issue an
agent grant. A cloud-only Claude session cannot reach your computer's loopback
address.

Claude Code accepts a project `.mcp.json` with an `mcpServers` wrapper. A stdio
entry contains `command`, `args` and `env`; environment placeholders can supply
credentials at launch. The instructions below preserve WMM's generated absolute
paths and register only WMM for the first session. See the current
[official MCP setup reference](https://code.claude.com/docs/en/mcp).

## 1. Prepare WMM and a read-only grant

In WMM, select the app and sign in as its owner. Open **Your agents → Manage
agent grants**, issue a short-lived grant containing `operations.read`, and
copy its once-only token into your password manager temporarily. Do not put it
in a prompt, file, command argument or repository.

Open **Review agent setup → Download reviewed setup JSON**. For a source
installation, this equivalent command runs from the WMM repository root in its
chosen Python environment; replace the origin with WMM's exact browser origin:

```powershell
python -m mission_control.agent_setup --origin http://127.0.0.1:8765 --json > wmm-setup.json
```

The source environment needs the pinned optional MCP dependencies in
[requirements-mcp.txt](requirements-mcp.txt). The installed desktop bundle
already includes them. Keep its generated executable/arguments; do not replace
them with a Python command.

**Manual inputs:** the actual setup-file path, once-only grant and selected app
ID belong to your installation. App ID is the grant's `app_id`, not the app's
display name. The remaining commands consume these inputs rather than assume
another machine's paths or account.

## 2. Register the generated entry

On Windows, paste this into PowerShell. Choose a private Claude working folder;
the script refuses to overwrite an existing project configuration.

```powershell
$setupPath = Read-Host 'Full path to the downloaded WMM setup JSON'
$workFolder = Read-Host 'Full path to your private Claude working folder'
New-Item -ItemType Directory -Path $workFolder -Force | Out-Null
Set-Location -LiteralPath $workFolder
$configPath = Join-Path (Get-Location) '.mcp.json'
if (Test-Path -LiteralPath $configPath) {
    throw 'Existing .mcp.json: manually merge only the WMM entry; do not overwrite other servers.'
}
$setup = Get-Content -LiteralPath $setupPath -Raw | ConvertFrom-Json
$entry = $setup.mcp_config.mcpServers.'wmm-local'
if (!$entry.command -or !$entry.args) { throw 'Use the complete WMM reviewed setup report.' }
if ($entry.args -notcontains '--use-grant') { throw 'Use the reviewed scoped-grant entry.' }
$entry.env | Add-Member -NotePropertyName WMM_AGENT_GRANT -NotePropertyValue '${WMM_AGENT_GRANT}' -Force
$config = @{mcpServers = @{wmm = $entry}} | ConvertTo-Json -Depth 20
[IO.File]::WriteAllText($configPath, $config, [Text.UTF8Encoding]::new($false))
```

Keep this machine-specific file private and out of version control. It contains
a credential **reference**, not the grant value. Preserve source `PYTHONPATH` and
all generated arguments, especially `--use-grant` and the exact origin.

For macOS/Linux, the equivalent **manual editor step** is to save the report's
`mcp_config` object as `.mcp.json` in your chosen Claude folder. Inside its WMM
entry's existing `env`, add `"WMM_AGENT_GRANT": "${WMM_AGENT_GRANT}"`; keep the
remaining entry unchanged. Its server name can stay `wmm-local`. Merge rather
than replace any existing configuration. This step requires no extra JSON CLI.

## 3. Launch with the grant in this process only

Confirm `claude auth status` reports a signed-in account. If necessary run
`claude auth login --claudeai` and complete the provider's sign-in. That browser
authentication and any workspace/MCP trust prompts are **manual steps**.

Windows PowerShell, from the folder containing `.mcp.json`:

```powershell
$grantInput = Read-Host 'Paste the WMM read-only grant' -AsSecureString
try {
    $env:WMM_AGENT_GRANT = [Net.NetworkCredential]::new('', $grantInput).Password
    claude --mcp-config .mcp.json --strict-mcp-config
} finally {
    Remove-Item Env:WMM_AGENT_GRANT -ErrorAction SilentlyContinue
    $grantInput.Dispose()
}
```

macOS/Linux Bash, from that folder:

```bash
read -r -s -p 'Paste the WMM read-only grant: ' WMM_AGENT_GRANT
printf '\n'
export WMM_AGENT_GRANT
claude --mcp-config .mcp.json --strict-mcp-config
unset WMM_AGENT_GRANT
```

The masked input avoids recording the value as a shell command. The grant still
exists temporarily in process memory/environment; this is not a credential vault.
Exit Claude when finished, clear any temporary password-manager copy, and revoke
the test grant in WMM. The project file alone never grants WMM access.

## 4. Make the first two calls inside Claude Code

Open `/mcp` and check the WMM server is connected. Approve only this reviewed
local server if Claude asks. A connected server proves transport discovery, not
permission to read an app.

Send these prompts separately, replacing the app ID in the second:

```text
Call the WMM tool wmm_catalog with {}. Return its actual result schema. Do not call any other tool.
```

```text
Call wmm_operations_read with {"app_id":"your-app-id","input":{}}. Return the actual app_id and schema. Do not call any other tool.
```

Both must return real tool data, with the second scoped to your selected app.
Catalog discovery alone is not app authorization. Additional writes, publication
and spending retain WMM's separate grant, review and campaign controls.

## Errors and the exact next step

| Claude Code symptom | Check next |
| --- | --- |
| `Not logged in` / asks for `/login` | Sign into this exact CLI installation; retry `claude auth status` before launching. |
| MCP server exits; `No module named mission_control` | Keep the generated absolute interpreter and `PYTHONPATH`; generate setup from the actual source environment, not another folder's Python. |
| Missing `mcp` / `anyio` | Source only: install the pinned optional requirements into the interpreter named by setup, then regenerate the report. |
| Connection refused / `ECONNREFUSED` | Start WMM separately and compare its exact `127.0.0.1` port with the entry's `--origin`. |
| Missing `WMM_AGENT_GRANT` / placeholder warning | Set the grant in the same shell that starts Claude; preserve the literal environment reference and start a fresh session. |
| App read denied / expired, revoked or exhausted grant | Check the selected app ID, `operations.read`, expiry and call allowance in WMM. Only the owner issues replacement authority. |
| Existing `.mcp.json` | Manually merge the one generated entry. This is an explicitly manual step, not an instruction to delete other servers. |

## Acceptance record

Record OS, Claude version, WMM version/source, SDK version, first failed step or
the two actual tool-result schemas, selected app ID and elapsed setup time.
Exclude grants, cookies and credentials. A clean-machine tester must follow only
this page and report the first instruction that is not usable as written.

The pinned MCP conformance baseline is separate from Claude-host acceptance.
The local Claude Code 2.1.207 launch reached its sign-in gate and recorded no
WMM tool calls; successful host calls and clean-machine acceptance are **not yet
verified**. The manual guide does not depend on the in-progress GUI connection
wizard. Return to the [agent quickstart](agent-quickstart.md) for other hosts.
