# Verify scoped access on the WMM owner host

Offline setup lists a verification command for source Python or its packaged counterpart. It continues to inspect dependencies without contacting WMM or reading a grant.

Supply the selected app ID with `--verify-app` and inject `WMM_AGENT_GRANT` through the host's protected process environment. The command makes one `operations.read` call through the existing exact-loopback scoped gateway. This read consumes one admitted grant attempt and records the usual gateway audit entry. It changes no app configuration and performs no provider read or external write.

A successful receipt identifies the CLI variant, exact origin, app, manifest revision, verified operation and remaining allowance. It does not return private source data, a grant ID or the full policy response. Missing credentials fail before networking. An unavailable service, mismatched app, revoked grant or malformed response fails without fallback authority or raw server text.

Run this from the authorized owner host or supported private SSH execution path. It verifies this reachable owner-host process and a scoped read only. Remote MCP, unattended availability, provider delivery and other operation permissions require their own evidence. Cloud-only agents still need a separate supported connection.

Acceptance: real synthetic loopback server, source and existing packaged dispatch paths, quota readback, wrong app and revoked grant, absent server, missing grant, and no bearer or private response in output.
