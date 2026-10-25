# Spec: funnel-transport
Status: implementation

## MUST - Functional core
### Requirements (EARS)
- The system shall return app-owned funnel definitions, observations and reports through `funnel_reads` using exact loopback routes and current owner identity or scoped grants.
- The system shall reject stale manifests and unreviewed operations through `funnel_writes`, revalidating current authority at transaction entry and commit for immutable plan saves and at most 500 observations per import.
- The system shall return the same durable funnel state through owner HTTP, CLI and official MCP through `funnel_clients` with a machine-readable nested input contract and without exposing a human approval tool or provider effect.
- The system shall reject unknown queries, encoded, malformed or foreign routes and unknown JSON fields through `funnel_boundaries`, with one exact JSON body of at most 1048576 bytes and a 5-second body deadline, while reads accept only one canonical offset query and return at most 100 rows per page.
- The system shall retain all six new operations in the local evidence workflow map through `funnel_automation`, preserving existing blockers and owner-selected review policies.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: funnel_reads
  Given an app-owned saved funnel
  When `funnel_reads` uses a current authorized identity
  Then only that app's exact saved state is returned
Scenario: funnel_writes
  Given a current app and declared funnel input
  When `funnel_writes` saves or imports
  Then stale or revoked authority cannot commit
Scenario: funnel_clients
  Given a scoped agent and a separate owner
  When `funnel_clients` operates through HTTP CLI and MCP
  Then each client sees the same immutable saved observations
Scenario: funnel_boundaries
  Given invalid framing path or app identity
  When `funnel_boundaries` admits a request
  Then it is rejected without new funnel data
Scenario: funnel_automation
  Given the fixed operation catalog
  When `funnel_automation` compiles workflow scope
  Then every operation is explicitly classified without removing unfinished-workflow blockers
```

## WON'T - Out of scope
No provider request, message, ad spend, publication, credential onboarding or live paywall change. UI, export and complete app-sales workflow acceptance remain separately required. Report timestamps are fresh observations and may differ between sequential reads; saved definitions and imported event identities remain identical.

## Pagination and input discovery
Definition lists return summaries and next_offset, total and limit100. Use the exact single-definition read for full saved inputs. Observation reads return at most100 rows with next_offset and total; reports still calculate from every bounded saved observation. Only list and observation reads accept offset from0 through10000 as a canonical decimal query; other reads reject queries. CLI/MCP expose this as a closed optional offset field. Reports never silently calculate from the first page. The operation catalog includes the full nested app-sales input field contract.
