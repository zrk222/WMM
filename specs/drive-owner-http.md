# Spec: drive-owner-http
Status: implementation; browser callback, UI and agent integration remain required

## MUST - Functional core
### Requirements (EARS)
- The system shall reject owner requests unless exact loopback host, origin, session, CSRF and fresh OWNER membership match, retaining role and session guards at transaction commit, identified by `drive_http_owner`.
- The system shall reject a callback whose parsed state hash does not belong to the route app before claiming the flow or exchanging credentials, identified by `drive_http_callback`.
- The system shall return bounded private setup, account review, confirmation, disconnect and cleanup results through exact canonical app routes without credential values, identified by `drive_http_lifecycle`.
- The system shall store imports through the existing durable owner-bound queue and return private job status and cancellation through exact app routes instead of downloading during an HTTP request, identified by `drive_http_jobs`.
- The system shall reject duplicate JSON keys, transfer encodings, duplicate framing headers, non-object inputs, unknown operations and bodies exceeding 16384 bytes within the existing 5 seconds read deadline, identified by `drive_http_input`.
- The system shall emit isolated real HTTP evidence for setup, synthetic consent exchange, exact account adoption, import queuing, privacy, cross-app callback denial and revoked owner authority without real Google requests, identified by `drive_http_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_http_owner
  Given an isolated app and verified owner session
  When `drive_http_owner` exercises its exact route contract
  Then required behavior and rejection boundaries are recorded
Scenario: drive_http_callback
  Given an isolated app and verified owner session
  When `drive_http_callback` exercises its exact route contract
  Then required behavior and rejection boundaries are recorded
Scenario: drive_http_lifecycle
  Given an isolated app and verified owner session
  When `drive_http_lifecycle` exercises its exact route contract
  Then required behavior and rejection boundaries are recorded
Scenario: drive_http_jobs
  Given an isolated app and verified owner session
  When `drive_http_jobs` exercises its exact route contract
  Then required behavior and rejection boundaries are recorded
Scenario: drive_http_input
  Given an isolated app and verified owner session
  When `drive_http_input` exercises its exact route contract
  Then required behavior and rejection boundaries are recorded
Scenario: drive_http_proof
  Given an isolated app and verified owner session
  When `drive_http_proof` exercises its exact route contract
  Then required behavior and rejection boundaries are recorded
```

## WON'T - Out of scope
No browser callback page, UI, CLI, MCP, automatic token refresh or autonomous grant is completed by this HTTP packet. No provider write, spending, publication or production activation.
