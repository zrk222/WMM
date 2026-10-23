# Spec: agent-cli
Status: draft

## MUST - Functional core
### Description
Provide a real generic-client CLI for existing local WMM upgrade services. A machine-readable catalog is shared by the client and future MCP adapter. This is an additive transport packet; complete authenticated agent grants, human checkpoint execution, full-domain catalog and MCP remain mandatory follow-up work.

### Requirements (EARS)
- The system shall return a versioned fixed catalog of supported local upgrade reads and writes with method, route, required fields and effect classification through `fixed_catalog`.
- The system shall reject noncanonical loopback origins, proxies and redirects and bound requests and responses to 16777216 bytes with a 15 seconds timeout while retaining only an in-memory session cookie and CSRF token through `loopback_client`.
- The system shall reject unknown operations, foreign route syntax and extra or missing envelope fields before transport, and submit exact app-owned payloads to existing server validators without automatic write retries through `typed_calls`.
- The system shall return JSON results or structured nonzero failures through a command-line entry using bounded strict stdin JSON, catalog and call commands, with no credentials in command arguments or saved session files through `cli_protocol`.
- The system shall reject attempts to invoke human approval, provider mutation, identity login, credential setup, spend or publication through the catalog and retain the incomplete full-agent-authorization state through `approval_boundary`.
- The system shall verify actual CLI subprocess and library flows through an isolated WMM HTTP server for saved growth/customer/journey/experiment data, malformed input, CSRF, scope and failure recovery through `real_client_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: fixed_catalog
  Given a selected local app and fixed operation catalog
  When `fixed_catalog` is exercised
  Then the valid result is returned and malformed or unauthorized routes cannot gain authority
Scenario: loopback_client
  Given a selected local app and fixed operation catalog
  When `loopback_client` is exercised
  Then the valid result is returned and malformed or unauthorized routes cannot gain authority
Scenario: typed_calls
  Given a selected local app and fixed operation catalog
  When `typed_calls` is exercised
  Then the valid result is returned and malformed or unauthorized routes cannot gain authority
Scenario: cli_protocol
  Given a selected local app and fixed operation catalog
  When `cli_protocol` is exercised
  Then the valid result is returned and malformed or unauthorized routes cannot gain authority
Scenario: approval_boundary
  Given a selected local app and fixed operation catalog
  When `approval_boundary` is exercised
  Then the valid result is returned and malformed or unauthorized routes cannot gain authority
Scenario: real_client_proof
  Given a selected local app and fixed operation catalog
  When `real_client_proof` is exercised
  Then the valid result is returned and malformed or unauthorized routes cannot gain authority
```

## SHOULD - Technical
- Reuse authoritative service/HTTP validation. No alternate database mutation or private owner activation. Read results are app-owned; snapshot exports are private local data.
- Stdout is JSON only; errors use stderr and nonzero status. No shell evaluation, environment credential loading, session persistence or automatic external requests.
- Reject duplicate keys/nonfinite values in input and output. Use fixed operation names and identifier path segments, never caller-supplied HTTP paths.

## Authorized parameters
MAX_BYTES = 16777216
TIMEOUT_SECONDS = 15
The following values are isolated subprocess/test fixture parameters, not production defaults or spending authority.
timeout = 30
min_retention_rate = 0.2
max_refund_fraction = 0.1
min_contribution_minor = 0
max_acquisition_minor = 5000
