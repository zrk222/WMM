# Spec: mcp-sdk-refresh
Status: draft

## MUST - Functional core
### Description
Refresh the optional MCP SDK to the patched maintenance release and verify real
WMM stdio clients in a clean Python environment. Preserve current authority and
the default dependency set. This does not claim an exploitable WMM vulnerability.

### Requirements (EARS)
- The system shall store optional MCP SDK version 1.30.0 in its dependency file and retain the default WMM dependency file unchanged through `sdk_pin`.
- The system shall return catalog discovery and shared CLI/MCP operation results using the selected SDK with current app and grant validation through `sdk_conformance`.
- The system shall reject stale grants, forbidden approval calls, invalid envelopes and replayed reviewed writes under the selected SDK through `sdk_authority`.
- The system shall reject unsupported adapter transports and return an actionable missing-dependency error without automatic installation or client registration through `sdk_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: sdk_pin
  Given optional MCP setup and the unchanged default dependency file
  When `sdk_pin` is installed in a clean environment
  Then the SDK reports version 1.30.0 and dependency checks succeed
Scenario: sdk_conformance
  Given actual CLI and official SDK stdio clients
  When `sdk_conformance` runs against isolated WMM services
  Then the clients read shared saved hashes and real worker outcomes
Scenario: sdk_authority
  Given invalid, revoked or stale scope and approval requests
  When `sdk_authority` validates calls
  Then existing denials and independent checkpoint boundaries hold
Scenario: sdk_boundary
  Given the optional adapter and an unconfigured SDK environment
  When `sdk_boundary` starts
  Then only stdio is offered and missing dependencies yield an actionable error
```

## Sources and applicability
Official upstream advisories GHSA-rwrf-2pqf-9j8j and GHSA-5h93-6whr-6q8j
identify 1.30.0 as the patched 1.x release. Their documented affected paths involve
SDK client schema resolution and HTTP clients; WMM exposes a stdio server and its
ClientSession usage is in controlled tests. Do not infer production exposure or
complete supply-chain assurance from the package version alone.
