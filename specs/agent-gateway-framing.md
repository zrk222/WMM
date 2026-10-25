# Spec: agent-gateway-framing
Status: implementation

## MUST - Functional core
### Description
Close the bearer call and reviewed prepare/status/resume HTTP framing gap found
by independent review. Keep exact origin, bearer and admission checks unchanged.

### Requirements (EARS)
- The system shall reject any Transfer-Encoding header including empty or duplicated values, duplicate Content-Type, and anything other than one application/json Content-Type and one decimal Content-Length from 1 through 16777216 before bearer admission through `gateway_framing`.
- The system shall read bearer call and reviewed prepare/status/resume and human Studio bodies within a cumulative 5 seconds through `gateway_body`, reject truncation or timeout including trickle senders before admission, close failed connections and restore the original socket timeout on success or error.
- The system shall reject each malformed Windows loopback `windows_framing_denial` before admission, and the framing test shall record `FRAMING_INVALID`, the exact handler path and the `Invalid` raised by a wrapper that calls the original framing validator.
- The system shall treat `windows_abort_outcome` as rejection only when the same request recorded that exact framing denial and the client raised `ConnectionAbortedError`, `ConnectionResetError` or `RemoteDisconnected`; when a response is available, the test shall require HTTP 400 and the existing rejection-body assertion.
- The system shall fail `empty_transfer_encoding_mutant` when the empty-Transfer-Encoding guard is removed, and the test shall reject `unmatched_client_abort` when no same-request server framing denial was recorded.

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
Scenario: windows_framing_denial
  Given one malformed framing request for a bearer call or reviewed route
  When `windows_framing_denial` reaches the original server framing validator
  Then the exact handler path and Invalid denial are recorded before admission
Scenario: windows_abort_outcome
  Given the server rejected the same malformed request before reading its body
  When `windows_abort_outcome` is a narrow client connection-abort exception
  Then only the matched server denial counts and any available response remains HTTP 400
Scenario: empty_transfer_encoding_mutant
  Given the empty Transfer-Encoding rejection is removed or a client abort has no matching denial
  When `empty_transfer_encoding_mutant` exercises the request harness
  Then the test fails rather than passing on an unrelated connection error
```

## SHOULD - Compatibility and proof
- Existing CLI and MCP clients send application/json without parameters.
- Reuse one body reader for ordinary call and all three reviewed actions.
- Use synthetic loopback requests, unit timeout restoration and existing real
  CLI/MCP grant/review suites. Do not contact providers or operational data.

## WON'T - Scope boundary
- No weaker origin, role, grant, standing authority or uncertain-effect behavior.
- No whole-repository security or release claim from the bounded repair.
