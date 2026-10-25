# Spec: agent-gateway-framing
Status: implementation

## MUST - Functional core
### Description
Close the bearer call and reviewed prepare/status/resume HTTP framing gap found
by independent review. Keep exact origin, bearer and admission checks unchanged.

### Requirements (EARS)
- The system shall reject any Transfer-Encoding header including empty or duplicated values, duplicate Content-Type, and anything other than one application/json Content-Type and one decimal Content-Length from 1 through 16777216 before bearer admission through `gateway_framing`.
- The system shall read bearer call and reviewed prepare/status/resume and human Studio bodies within a cumulative 5 seconds through `gateway_body`, reject truncation or timeout including trickle senders before admission, close failed connections and restore the original socket timeout on success or error.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: gateway_framing
  Given an empty or duplicated transfer encoding or content type
  When `gateway_framing` handles an exact bearer route
  Then the request rejects before grant admission or reviewed dispatch
Scenario: gateway_body
  Given an incomplete or stalled bearer body
  When `gateway_body` reads the declared length
  Then no operation is admitted and the previous timeout is restored
```

## SHOULD - Compatibility and proof
- Existing CLI and MCP clients send application/json without parameters.
- Reuse one body reader for ordinary call and all three reviewed actions.
- Use synthetic loopback requests, unit timeout restoration and existing real
  CLI/MCP grant/review suites. Do not contact providers or operational data.

## WON'T - Scope boundary
- No weaker origin, role, grant, standing authority or uncertain-effect behavior.
- No whole-repository security or release claim from the bounded repair.
