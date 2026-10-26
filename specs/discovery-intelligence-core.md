# Spec: discovery-intelligence-core
Status: implementation; UI, CLI/MCP and authorized collector scheduling integration remain REQUIRED
Parent: user-approved SpyTok P1/P2 recommendations; no prior goal scope removed.

## MUST - Functional core
### Requirements (EARS)
- The system shall store separate industry, narrative and production-treatment classifications with original labels and analyst or agent rationale, binding each review to an exact app version and immutable source capture hash with at most 24 items in original labels, identified by `discovery_taxonomy`.
- The system shall store permitted timestamped transcripts, observed hook and beats, interpreted mechanism, reproduction requirements, authentic app evidence references, rights status and proposed next experiment separately from observed source facts, rejecting unsupported fields and transcript segments outside their declared duration with at most 200 items in segments, identified by `discovery_source_review`.
- The system shall return inclusion and exclusion reasons for every inspected source using outcome/audience intent, taxonomy, publication window, observation freshness, minimum views and documented baseline availability, preserving 100000 views AND 10 times a documented comparable creator median for viral eligibility, identified by `discovery_query`.
- The system shall store immutable app-scoped saved queries and collection snapshots with exact deduplicated source hashes, observation dates, coverage status and independent candidate qualification baseline-missing rights-missing counts, returning explicit empty failed or stale states without altering historical snapshots, identified by `discovery_collections`.
- The system shall return separately labeled reach, comparable engagement, observed velocity and documented creator-relative outlier values with transparent numerators denominators and observation windows, leaving unsupported or missing inputs unknown and never deriving installs revenue or causal lift, using at most 1000 items in source captures, identified by `discovery_rankings`.
- The system shall reject a production handoff after current app source or review hashes change or required rights authentic evidence and viral qualification are missing; return a prepared evidence-card packet that does not execute render publication or external changes, identified by `discovery_handoff`.
- The system shall store explicitly authorized creator or competitor watch definitions and append source-level successful failed empty and stale collection attempts without inferring a supplier API or automatically scheduling external reads in this core packet, identified by `discovery_watch_history`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: discovery_taxonomy
  Given app-owned permitted source captures
  When `discovery_taxonomy` evaluates exact current inputs
  Then independent source observations decisions and execution boundaries are retained
Scenario: discovery_source_review
  Given app-owned permitted source captures
  When `discovery_source_review` evaluates exact current inputs
  Then independent source observations decisions and execution boundaries are retained
Scenario: discovery_query
  Given app-owned permitted source captures
  When `discovery_query` evaluates exact current inputs
  Then independent source observations decisions and execution boundaries are retained
Scenario: discovery_collections
  Given app-owned permitted source captures
  When `discovery_collections` evaluates exact current inputs
  Then independent source observations decisions and execution boundaries are retained
Scenario: discovery_rankings
  Given app-owned permitted source captures
  When `discovery_rankings` evaluates exact current inputs
  Then independent source observations decisions and execution boundaries are retained
Scenario: discovery_handoff
  Given app-owned permitted source captures
  When `discovery_handoff` evaluates exact current inputs
  Then independent source observations decisions and execution boundaries are retained
Scenario: discovery_watch_history
  Given app-owned permitted source captures
  When `discovery_watch_history` evaluates exact current inputs
  Then independent source observations decisions and execution boundaries are retained
```

## Architecture and bounds
Each app retains at most2000 immutable research documents with at most100 revisions per document. Collection evaluation inspects at most1000 app sources. Transcript and beat lists contain at most 200 items in segments each. Reviews store at most 24 items in original labels and at most24 authentic evidence references. A transcript contains at most100000 characters; each segment contains at most2000 characters. All writes bind current app/source state inside the final SQL transaction. Existing source permission records do not independently verify legal rights.

## WON'T - Out of scope of core packet
No provider API is inferred from public SpyTok pages. No provider request, autonomous scheduling, native video production, publication or measured app sale is authorized by a research snapshot. Full UI and CLI/MCP parity and authorized collector/schedule execution remain required follow-up implementation. UGC intake remains exempt from viral discovery qualification.

## User acceptance boundaries
Viral-only means 100000 views AND 10 times a documented comparable creator baseline. High-view examples and third-party outlier labels remain candidates until qualified. UGC intake is exempt from viral-only discovery eligibility. Saved research never grants reuse approval, production execution, publication or measured app sales. Human and standing downstream authority is rechecked by the existing action-specific controls. Research recommendations are not delivered functionality until implemented, tested and hash-bound through CF.
