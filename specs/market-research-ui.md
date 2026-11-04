# Spec: market-research-ui

## MUST - Functional core
### Description
Expose source-backed keyword and competitor research in the existing growth
review GUI, immutable entry store and reports. Personal agents use the existing
growth.save operation and inspect a typed catalog contract. No new tools or engine.

### Requirements (EARS)
- The system shall return the current market research schema in the existing catalog through `market_contract`, without adding an operation.
- The system shall accept a local JSON research file through `market_import` up to 1 MiB, preserve its raw JSON for server validation and show an app-bound summary before explicit saving.
- When app context changes, the system shall reject the pending research form through `market_context`, retaining its local inputs and immutable request identity for inspection.
- The system shall return source provenance, keyword coverage, competitor overlap, unknown metrics and proposed experiments through `market_readout` in saved details and existing JSON and PDF reports.
- The system shall return actionable file and server errors through `market_recovery`, keeping local inputs and creating no duplicate entry for an identical request and no source-derived authority to publish or spend.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: market_contract
  Given a personal agent reading the current catalog
  When it inspects market research input
  Then it can prepare the exact growth.save envelope without a new tool
Scenario: market_import
  Given a permitted local research file for the current app
  When the operator reviews and saves its summary
  Then the original JSON reaches strict server validation and immutable saved evidence is returned
Scenario: market_context
  Given an open pending form
  When app context changes
  Then saving is rejected and existing app records remain unchanged
Scenario: market_readout
  Given a saved keyword research entry
  When the operator opens details and exports reports
  Then evidence links and analyst findings remain distinct from measured demand or outcomes
Scenario: market_recovery
  Given malformed research or an uncertain response
  When the operator corrects or retries the exact request
  Then the error is actionable and immutable history contains no duplicate
```

## Authorized parameters
MARKET_FILE_BYTES = 1048576

## Non-goals
No new provider collection, publication, paid action, keyword-rank prediction or
guaranteed growth. Imported observations remain operator assertions.
