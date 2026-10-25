# Spec: funnel-founder
Status: implementation

## MUST - Functional core
### Requirements (EARS)
- The system shall return a current app-sales founder review through `founder_read`, joining the existing subscription-review source receipt with at most 5 rows per page of exact funnel reports while retaining app, cohort, currency, stage coverage, source status and report hashes separately.
- The system shall reject unauthorized and malformed founder reads through `founder_authority` using the existing exact owner or scoped grant boundary, one canonical offset from0 through10000, current authority at datastore reads and no private funnel projection into public workspace or portfolio responses.
- The system shall return explicit repair findings through `founder_gaps` for absent plans, missing, partial, unknown, stale or corrupt sources and withheld comparisons, showing at most20 findings per funnel and100 base findings with total and remaining coverage disclosed.
- The system shall return the same source-bound review through `founder_clients` in owner HTTP, CLI and official MCP, classify the new read operation without loosening automation blockers and reject unknown inputs or foreign app scope.
- The system shall render the founder review through `founder_ui` from Results with labelled desktop and mobile controls, scoped late-response rejection, exact funnel detail links, bounded pagination and PDF JSON CSV exports of displayed coverage without inventing changes since a previous review or causal sales lift.
- The system shall reject a changed app context through `founder_consistency` after sequential source reads, retain unavailable individual funnel rows instead of dropping them, and perform0 provider writes or automatic repair actions.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: founder_read
  Given current subscription evidence and saved app-sales funnels
  When `founder_read` evaluates a page
  Then each source receipt and currency remains distinct with complete page coverage
Scenario: founder_authority
  Given absent revoked or foreign authority or a malformed raw address
  When `founder_authority` admits a review request
  Then no private founder evidence is returned
Scenario: founder_gaps
  Given missing partial unknown stale or corrupt funnel evidence
  When `founder_gaps` prepares next actions
  Then every unavailable source remains visible with exact bounded coverage and repair guidance
Scenario: founder_clients
  Given a scoped agent and an independent app owner
  When `founder_clients` reads through HTTP CLI and MCP
  Then declared source identities and observation results agree without granting effects
Scenario: founder_ui
  Given desktop and narrow mobile Results screens
  When `founder_ui` opens pages detail links and reports
  Then source status and exports agree and foreign or late context cannot replace the current view
Scenario: founder_consistency
  Given source reads underway for one app version
  When `founder_consistency` sees changed app setup
  Then the review is rejected without discarding history or claiming an atomic snapshot
```

## WON'T - Out of scope
No anonymous access to private funnel reports, global financial rollup across currencies, prior-review performance delta, provider dispatch, ad spending, publication or live paywall changes. Real provider acceptance, private activation and remaining original/additive goal requirements remain separately required.
