# Spec: hypit-session-transport
Status: draft

## MUST - Functional core
### Description
Connect the internal owned-session manager to one long-lived server Service and
shared human/agent operation transports. Implement seven operations now; the eighth
restart reconciliation operation remains required and unexposed until stopped
resource inspection is trustworthy. Do not substitute a successful transport for
complete human editor or full workflow acceptance.

### Requirements (EARS)
- The system shall route Studio plan start sessions read edit inspect and close operations to one Service-owned manager through `transport_shared`.
- The system shall reject human Studio calls without fresh verified OWNER identity exact JSON framing current CSRF and app scope through `transport_owner`.
- The system shall reject agent Studio operations outside exact ordinary reviewed or standing grant scope through `transport_agent`.
- The system shall return the same fixed typed operation results through actual CLI and MCP protocol clients without native authority in client subprocesses through `transport_clients`.
- The system shall return explicit UNKNOWN recovery guidance for uncertain native work with a mutation deadline of 20 seconds through `transport_unknown`.
- The system shall reject new manager admission and store confirmed or unresolved owned cleanup before releasing server resources through `transport_shutdown`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: transport_shared
  Given multiple human and agent calls on the same server
  When `transport_shared` selects a session
  Then the same actual owned manager and durable source state are used
Scenario: transport_owner
  Given unsigned wrong-role foreign-app or ambiguous JSON input
  When `transport_owner` handles the human route
  Then it rejects before native work
Scenario: transport_agent
  Given current ordinary reviewed or standing approval scope
  When `transport_agent` executes a Studio operation
  Then existing exact admission and uncertainty semantics remain enforced
Scenario: transport_clients
  Given real CLI and MCP clients connected to the loopback server
  When `transport_clients` read and inspect app-owned sessions
  Then fixed schemas and current saved states agree without client-native startup
Scenario: transport_unknown
  Given an uncertain startup edit or close
  When `transport_unknown` returns to the client
  Then explicit reconciliation guidance is returned without another native call
Scenario: transport_shutdown
  Given owned sessions and server shutdown
  When `transport_shutdown` closes the server
  Then manager cleanup result is retained before the listening resources close
```

## Routes and effects
Human operations use POST /api/apps/{app}/studio/{action} for plan/start/sessions,
and POST /api/apps/{app}/studio/{session}/{action} for read/edit/inspect/close.
All require CSRF-protected local session, exact origin/host, one Content-Length,
application/json, no query/transfer encoding, fresh GitHub identity and OWNER role.
Using POST for read-only private session observations allows identical finite
envelopes and fresh identity checks. Agent callers use the existing bearer gateway;
catalog discovery grants no authority. studio.start is native local execution,
studio.edit changes private source and studio.close stops owned local resources.
No reconciliation route or arbitrary native command is exposed.

The existing executable standing local-evidence scope does not include Studio.
The incomplete video-authoring workflow remains blocked for standing activation;
adding transport descriptors must not expand an already approved policy. Full
standing video operation remains a parent requirement after complete workflow
readiness is implemented and verified.

## Shutdown
Service owns exactly one manager instance. Server close first tells it to stop
admission and coordinate in-flight work. Confirmed cleanup is retained; a timeout
or failed cleanup remains explicit in service shutdown receipts and durable
registry metadata. Closing the listening socket must not be reported as complete
native cleanup. Standalone CLI/MCP tools remain HTTP clients of the server manager.

Studio transport and exact reviewed resume use a fixed 900-second HTTP observation
deadline to cover fingerprinting/preparation plus native startup/cleanup. This does
not change native startup45/read2/mutation20/command120-second deadlines. All other
client calls retain the existing15-second default. No automatic retry is added.
