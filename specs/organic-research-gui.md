# Spec: organic-research-gui

## MUST - Functional core
### Description
Expose existing bounded external-agent research and owner intake through the
operational Research screen. Reuse exact owner HTTP, collector, discovery and
intake services; create no provider crawler, publication authority or second
research engine. Preserve the commercial GUI contract and remaining workflows.

### Requirements (EARS)
- The system shall display app-and-owner-scoped paginated research tasks and saved intake receipts through `research_history`, excluding credentials and other owners' tasks.
- When a current owner assigns research, the system shall prepare one exact task for an existing eligible agent grant through `research_assignment`, displaying selected platforms, permitted access, expiry within 24 hours and bounds of 1 through 20 candidates, 1 through 500 reads and 1 through 3600 seconds.
- The system shall display reported candidates, qualification, baseline gaps, rights gaps, source failures and collection state through `research_results`, retaining at least 100000 views AND 10 times the documented median of at least 10 comparable prior posts and the separate UGC intake path.
- When an owner approves a qualified research candidate, the system shall submit structured inspection, app proof and experiment fields to the existing exact intake through `research_adoption`, without granting media reuse, production or publication authority.
- When a response is uncertain or app, role or source context changes, the system shall retain up to 25 exact requests for explicit inspection or identical retry and reject stale actions through `research_recovery`, with a 30000 ms response timeout and 0 automatic write retries.
- The system shall return keyboard-usable 1440px and 390px research controls, actionable empty/error states and redacted JSON and PDF reports through `research_accessibility`, using existing product styles and report services.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: research_history
  Given saved tasks for different apps and owners
  When a fresh owner opens research history
  Then only that owner's tasks in the selected app appear with bounded pagination and saved adoption receipts
Scenario: research_assignment
  Given an eligible existing agent grant for claim and submit
  When the owner reviews and assigns a research task
  Then its exact query and finite bounds are saved once without collecting, downloading or publishing media
Scenario: research_results
  Given submitted candidates with qualified, baseline-missing, rights-missing and UGC states
  When the result screen opens
  Then observed counts and failures remain distinct and only a current qualified relevant reference offers research adoption
Scenario: research_adoption
  Given a qualified reported candidate and authentic app evidence
  When the owner confirms direct inspection and saves its structured research review
  Then the exact task and candidate hashes bind the saved source, review, collection and analysis while reuse and publication remain unapproved
Scenario: research_recovery
  Given an uncertain save or changed app or owner context
  When a late response, inspection or explicit identical retry occurs
  Then stale results cannot replace the current screen and no changed write or automatic retry is sent
Scenario: research_accessibility
  Given the actual rendered research controls at desktop and mobile widths
  When an operator uses keyboard, validation, history, review and export controls
  Then focus, error messages, reports and source decisions remain usable without horizontal page overflow
```

## Authorized parameters
RESEARCH_PAGE_SIZE = 20
RESEARCH_MAX_OFFSET = 100000
RESEARCH_REQUEST_TIMEOUT_MS = 30000
RESEARCH_DEFAULT_CANDIDATES = 5
RESEARCH_DEFAULT_READS = 100
RESEARCH_DEFAULT_SECONDS = 600
RESEARCH_DEFAULT_MINUTES = 30
RESEARCH_PENDING_LIMIT = 25
RESEARCH_MAX_CARD_TEXT = 4000
MIN_VIEWS = 100000
MULTIPLIER = 10
MIN_BASELINE = 10

## Non-goals
No new supported platforms, external agent host installation, automatic grant
issuance, foreign-media download, new publication effects or numerical growth
claims. UGC keeps its existing media-library flow and viral exemption. Full
policy, production, scheduling and monitoring GUI remain subsequent packets.
