# Spec: desktop-entry
Status: draft

## MUST - Functional core
### Description
A terminal-free desktop entry over the existing loopback WMM server. Bundled runtime builds are separate CI artifacts, never claimed from source tests alone.

### Requirements (EARS)
- The system shall store packaged desktop data in the current user application-data directory outside bundled resources through `private_data`.
- The system shall bind only to literal IPv4 loopback and open the actual bound port in the default browser through `loopback_only`.
- When the owner closes the desktop controller, the system shall stop workers and close the local server through `clean_shutdown`.
- The system shall route explicit agent CLI and MCP arguments through the packaged executable, including MCP initialization, discovery, ping and catalog access without a workspace through `frozen_dispatch`.

- The system shall include its Linux protected-storage dependency in native bundles and return a successful synthetic native credential roundtrip with verified cleanup through `bundled_vault`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: private_data
 Given a packaged launch
 When `private_data` launches or closes the desktop
 Then the writable database path belongs to current user data
Scenario: loopback_only
 Given an occupied preferred port
 When `loopback_only` launches or closes the desktop
 Then the selected actual loopback port is opened without exposing a host interface
Scenario: clean_shutdown
 Given a running packaged desktop process
 When `clean_shutdown` launches or closes the desktop
 Then the local listener and worker threads terminate without deleting saved data
Scenario: frozen_dispatch
 Given a frozen agent command
 When `frozen_dispatch` launches or closes the desktop
 Then the existing adapter executes without requiring a system Python command
Scenario: bundled_vault
 Given a clean native runtime and unlocked isolated user secret store
 When `bundled_vault` writes reads and removes one synthetic unique credential
 Then the expected value is read and its deletion verified without returning its contents
```

## SHOULD - Technical
- Reuse Store, Server and existing protected vaults; do not copy owner data or credentials into a bundle.
- Prefer small folder-mode native bundles, build on remote matching platforms and avoid local heavy downloads.
- No public host or reverse proxy, no automatic provider execution and no silent startup registration.

## Authorized parameters
timeout = 90
