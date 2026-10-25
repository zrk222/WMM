# Spec: personal-agent-operations
Status: draft

## MUST - App-scoped personal agent guide
### Requirements (EARS)
- The system shall return four unique personal agent profiles with primary documentation and classified connection capabilities through `profile_contract`.
- The system shall bind guide hashes to current app data, manifest version, catalog and policy through `guide_scope`.
- The system shall expose the guide through HTTP, CLI and MCP operations.read without network or credential access during discovery through `guide_discovery`.
- The system shall return explicit grant, checkpoint, UNKNOWN recovery and unsupported workflow boundaries through `guide_authority`.

- The system shall return the actual creative_taste policy hash and five laws with current public app preference bindings and advisory authority through `taste_delivery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: profile_contract
  Given four personal agent hosts
  When `profile_contract` emits profiles
  Then each has unique identity and primary URLs with verified and unknown capability classifications
Scenario: guide_scope
  Given a changed app hash or version
  When `guide_scope` emits the guide
  Then its scope and guide hash change
Scenario: guide_discovery
  Given an isolated local server
  When `guide_discovery` reads operations through HTTP CLI and official MCP
  Then the same scoped guide is returned without contacting providers
Scenario: guide_authority
  Given unsupported provider actions and an uncertain write
  When `guide_authority` describes execution
  Then current grants and checkpoints remain required and automatic resend remains forbidden
Scenario: taste_delivery
  Given current public app preferences
  When `taste_delivery` emits the guide
  Then actual taste policy and five laws remain advisory and execution integration remains incomplete
```

## Authorized parameters
APP = 1
Synthetic fixture APP = 1 denotes the initial app manifest version. Exactly four hosts. Ask at most three material questions after reading existing context.
No network, credential loading, provider activation or scheduling during discovery.
