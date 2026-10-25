# Spec: agent-mcp
Status: draft

## MUST - Functional core
### Description
Expose the existing fixed local upgrade operation catalog through an optional Python MCP stdio adapter using the installed official SDK. Keep CLI and MCP operation validation and authoritative WMM HTTP services shared. Full-domain coverage, authenticated scoped agent grants and independent human checkpoint dispatch remain required integration work.

### Requirements (EARS)
- The system shall return the catalog and every fixed operation as MCP tools with closed argument schemas and effect annotations through `mcp_discovery`.
- The system shall execute each tool through the existing OperatorClient and return JSON results through `shared_execution`.
- The system shall reject unknown tools, extra fields, hostile identifiers, invalid billing scope and server-rejected data without bypassing authoritative validation through `mcp_validation`.
- The system shall serve MCP initialization, tool discovery, calls and shutdown over stdio using the official SDK without changing the default WMM dependency set through `stdio_lifecycle`.
- The system shall preserve per-call session isolation, no automatic write retries and no provider, identity, credential or human-approval tools through `authority_boundary`.
- The system shall return identical saved-history hashes to CLI and MCP clients using actual subprocesses and an isolated WMM server through `two_client_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: mcp_discovery
  Given an isolated local WMM workspace
  When `mcp_discovery` is exercised
  Then the declared tool catalog and effect classifications match the shared operation catalog
Scenario: shared_execution
  Given an isolated local WMM workspace
  When `shared_execution` is exercised
  Then saved local data is returned through the authoritative HTTP service
Scenario: mcp_validation
  Given malformed tool arguments or stale evidence
  When `mcp_validation` is exercised
  Then the call fails and existing saved history remains intact
Scenario: stdio_lifecycle
  Given a real SDK client and MCP subprocess
  When `stdio_lifecycle` is exercised
  Then initialization and tool calls complete and the subprocess terminates on session shutdown
Scenario: authority_boundary
  Given a tool caller requesting approval or provider actions
  When `authority_boundary` is exercised
  Then the request fails without gaining execution authority
Scenario: two_client_proof
  Given one shared app workspace and two different transport clients
  When `two_client_proof` is exercised
  Then both clients read the same immutable saved source hashes and retain app isolation
```

## SHOULD - Technical
- Optional dependency mcp==1.30.0 is the tested maintenance SDK baseline in a clean isolated environment; imports fail with an actionable error when absent. No dependency installation or client registration happens automatically. The running preview and global Python are separate installations.
- Only stdio is exposed. No additional listening server, raw route tool, shell, OAuth or credentials. Explicit canonical loopback origin remains required.
- Tool data is private local workspace content; connecting a model host shares returned content with that host under its settings. Tool annotations describe effects and do not enforce independent human approval.
- Existing transport limits remain MAX_BYTES = 16777216 and TIMEOUT_SECONDS = 15. Test subprocess timeout = 30; async fixture timeout = 45. No throughput or latency claim.
