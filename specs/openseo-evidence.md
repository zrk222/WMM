# Spec: openseo-evidence
Status: implemented; controlled provider, scoped-agent and desktop/mobile browser acceptance verified; live account acceptance separate

## MUST - Functional core
### Description
Use OpenSEO evidence in WMM's existing app-scoped report to choose and measure a web acquisition experiment without confusing Google results with App Store observations.

### Requirements (EARS)
- When an owner or scoped agent imports a web research packet, the system shall accept bounded normalized OpenSEO evidence that cites exact captured sources through web_import.
- When a saved OpenSEO observation is surfaced, the system shall show its metric units, source, observation date and capture state through web_report.
- If evidence is stale, partial, absent or missing a supporting source, the system shall withhold a ready recommendation through web_unknown.
- While evaluating web research, the system shall never copy Google rankings, search volumes or GA4 events into ASO or native attribution through web_isolation.
- When a user reviews an observation, the system shall offer a measurable next action with native outcomes only when verified separately through web_action.
- When the top recommendation has comparable scoped rate evidence, the system shall show one change, its exact baseline, a same-scope comparison and a decision checklist in the report and its exports through web_action_brief.
- When an owner connects OpenSEO inside WMM, the system shall protect its key, check the actual Search Console property, and retain a bounded app/market-scoped observation through native_read.
- When a scoped agent requests web research, the system shall enforce the current app/source grant and save only an exact retained source receipt through native_agent.
- If provider rows contain unsupported parameterized pages or pages outside this app, the system shall retain safe rows, disclose omission counts and mark the entire reading partial without merging page identities through native_omissions.
- If the app website or native source changes, the system shall withhold stale native recommendations through native_drift.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: web_import
  Given an web research packet with current captured sources
  When web_import processes supported normalized OpenSEO evidence
  Then the scope remains bound to the selected app and release
Scenario: web_report
  Given a saved OpenSEO observation
  When web_report projects it
  Then its source and metric units appear in the report and private export
Scenario: web_unknown
  Given an incomplete or stale source
  When web_unknown projects it
  Then evidence repair is recommended before a test
Scenario: web_isolation
  Given a Google position and a web conversion count
  When web_isolation projects them
  Then no ASO rank, app install or paid subscription is created
Scenario: web_action
  Given current Google Search Console evidence for a landing page
  When web_action ranks proposed actions
  Then the operator receives one web hypothesis and measurement step
Scenario: web_action_brief
  Given a complete owned search query or store-link rate and no unresolved same-page source issue
  When web_action_brief projects the highest ranked recommendation
  Then the draft preserves the original counts, window, scope and source hash and grants no external action
Scenario: native_read
  Given an owner-confirmed dedicated OpenSEO project
  When native_read retrieves final Search Console data
  Then the source matches this app website and no billable tools are dispatched
Scenario: native_agent
  Given a scoped agent with web research operations
  When native_agent reads and saves one retained provider reading
  Then its immutable app-bound report cites that exact source
Scenario: native_omissions
  Given clean app pages and unsupported parameterized or unrelated pages
  When native_omissions selects evidence
  Then clean rows remain distinct, omitted values stay private and coverage is partial
Scenario: native_drift
  Given retained native evidence and a changed connection
  When native_drift projects the report
  Then a recheck replaces actionable rates without changing history
```


