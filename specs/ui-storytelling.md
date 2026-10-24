# Spec: ui-storytelling
Status: draft

## MUST - Functional core
### Description
Apply Nanna product storytelling as plain factual guidance across WMM pages and
shared task dialogs. Explain mission, inputs, useful output and next choice while
preserving exact system state, cost, consent and existing operation controls.

### Requirements (EARS)
- The system shall display a distinct factual mission, inputs, delivered output and next action for each of the 10 navigation pages through `page_stories`.
- The system shall display purpose and result guidance for every statically declared task form in the shared dialog using an explicit form narrative map through `dialog_stories`.
- The system shall return escaped narrative text without form values, credentials or unobserved claims through `truth_boundary`.
- The system shall display readable desktop and mobile guidance alongside unchanged submit, cancel, permission, error and report controls through `user_agency`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: page_stories
  Given the current navigation page inventory
  When `page_stories` is displayed
  Then every page has its own mission, inputs, output and next action
Scenario: dialog_stories
  Given the current task form inventory
  When `dialog_stories` decorates each shared modal
  Then every form uses explicit contextual guidance without changing its controls
Scenario: truth_boundary
  Given malicious titles and private field contents
  When `truth_boundary` renders guidance
  Then titles remain text and field contents are never copied into guidance
Scenario: user_agency
  Given desktop and mobile page and dialog flows
  When `user_agency` reads guidance and submits or cancels
  Then controls, errors, reports and saved data behavior still work
```

## SHOULD - Technical
- Use the Nanna mission/guidance/agency/payoff arc without theatrical filler.
  State real product behavior directly. No invented growth, universal support,
  user results, cost savings or emotional pressure. Unknown results remain unknown.
- Centralize narrative definitions in a data-only UI module. Existing page-report
  purpose/next-action and analytics stay in place. Add page story beside the page
  guide and dialog story in the existing shared modal before showing it.
- For read-only dialogs without forms, orient the user to the exact displayed
  title and distinguish inspection from an action. Do not infer an effect from
  the title. Existing exact pre-action summaries remain authoritative.
- No audio provider or speech synthesis is invoked. This request is written UX
  narration. No credentials, permissions, provider actions or global preferences
  change from viewing a story. Unsupported future forms require narrative mapping.

## Authorized parameters
PAGE_COUNT = 10
timeout = 15
