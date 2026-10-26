# Spec: discovery-transport
Status: implementation
Parent: discovery-intelligence-core and all original/additive WMM goal requirements.

## MUST
### Requirements (EARS)
- The system shall expose exact owner-bound research review save, collection save, watch save, attempt save, prepared handoff, document read and paged history through `discovery_owner`, rejecting malformed paths and bodies over 1048576 bytes before domain writes.
- The system shall return the same research results through scoped grant CLI and official MCP using `discovery_clients`, preserving existing exact human review, standing authority and at most 1 request per operation without adding any approval tool.
- The system shall return at most 100 items in history summaries per page using `discovery_history`, with explicit current app/source/review state separate from immutable snapshots and bounded offsets from 0 through 2000.
- The system shall return machine-readable nested research field contracts and viral policy through `discovery_contract`, preserving both 100000 views and 10 times documented creator baseline and keeping UGC intake exempt.
- The system shall return the classification of all new operations as local research evidence through `discovery_automation`, preserving live collector scheduling and publication blockers without treating saved research as execution or measured app sales.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: discovery_owner
  Given a current app owner and permitted synthetic sources
  When `discovery_owner` saves or reads exact research
  Then only current authorized app state is returned or committed
Scenario: discovery_clients
  Given an owner and a scoped agent
  When `discovery_clients` uses CLI and official MCP
  Then durable saved research is identical and authority checks remain enforced
Scenario: discovery_history
  Given immutable saved documents
  When `discovery_history` reads a selected page
  Then summaries retain hashes and bounded coverage without private text
Scenario: discovery_contract
  Given the fixed operation catalog
  When `discovery_contract` is requested
  Then exact input fields and execution boundaries are discoverable
Scenario: discovery_automation
  Given existing standing workflow scopes
  When `discovery_automation` inventories operations
  Then each local research operation is classified and unsupported effects remain blocked
```

## Bounds
One exact canonical loopback host and origin; fresh owner cookie and CSRF or an existing scoped agent grant. Research documents remain at most2000 rows per app and100 revisions per identity. Writes retain the core app/source checks and existing transaction authority guards. Permission to save research is never reuse permission, production, publication or measured sales.

## Remaining parent scope
UI, brief/editor/Hypit wiring, authorized provider collectors and actual scheduling, real clients/devices and full platform acceptance remain required. This transport cannot initiate provider reads or approve an action.
