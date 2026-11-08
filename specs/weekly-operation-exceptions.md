# Spec: weekly-operation-exceptions
Status: draft

## MUST - Functional core
### Description
Extend the existing five-app weekly exception inbox with owner-scoped saved operational exceptions. The projection reads local state only, never executes work and leaves intentional OFF states quiet.

### Requirements (EARS)
- The system shall return existing P0 and evidence gates unchanged while inspecting at most 5 apps per weekly page through `legacy`.
- The system shall reject private operational projection without a trusted current authenticated principal and active app OWNER role through `owner_only`.
- The system shall return stable deduplicated actionable cards for UNKNOWN or PENDING campaign delivery, blocked monitors or report plans and active resources with expiry at or before observation time needing a decision through `actionable`.
- The system shall return zero operational alerts for intentional OFF and completed finite work through `quiet`.
- The system shall return fixed action tools, exact owned resource IDs, source hashes and observation dates without credentials or raw operation payloads through `privacy`.
- The system shall project, separately from exceptions and only for the active app owner, current local queued or running jobs, waiting saved sequences and approvals expiring within seven days through `active_work`, with bounded per-source reads, app coverage, the saved update time, the stored expiry when present and one fixed next action.
- The system shall never infer a completed result from a queued, running or waiting state and shall keep active work out of the exception count.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: legacy
  Given a portfolio with existing P0 and evidence gaps
  When `legacy` reviews a weekly page
  Then existing ordering, five-app coverage and no-execution authority remain
Scenario: owner_only
  Given anonymous, maker and current owner identities
  When `owner_only` projects saved operational state
  Then only the active app owner receives private resource references
Scenario: actionable
  Given unknown delivery, blocked work and expired active pending resources
  When `actionable` creates cards
  Then cards have stable IDs, concrete repair actions and no repeated target duplicates
Scenario: quiet
  Given intentionally OFF scopes and finished finite plans
  When `quiet` reviews unchanged normal work
  Then no operational alert is created
Scenario: active_work
  Given owner-scoped queued or running jobs, waiting sequences and approvals expiring within seven days
  When `active_work` projects the weekly page
  Then each item carries app coverage, the saved update time, expiry when stored and one fixed next action
  And no payload, result or credential is disclosed
  And non-owner identities receive none
Scenario: privacy
  Given credential-like raw error and request payloads
  When `privacy` projects exceptions
  Then only fixed public state and owned receipt identities are returned
```

## SHOULD - Technical
- review(service,offset=0,user=None) requires trusted session user from the HTTP adapter; caller names or query parameters never select authority.
- Root wires existing local identity into the route. Default anonymous behavior retains legacy evidence checks without private operational references.
- Reads are bounded by 50 scopes, monitors and report plans plus 100 intents per kind per selected app. No table creation, provider read or external message.
