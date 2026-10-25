# Spec: studio-control-ui
Status: draft

## MUST - Functional core
### Description
Expose existing protected Studio operations in the creative workspace. Render
all compiled controls without source paths or arbitrary native browser access.
This UI does not substitute for full semantic authoring, native preview isolation,
render/export of edited projects, or restart reconciliation.

### Requirements (EARS)
- The system shall render saved sessions and exact source execution summaries before one confirmed startup through `studio_summary`.
- The system shall render every compiled field with its label current value and writable state through `studio_fields`.
- The system shall send an exact source-head and compiled-view bound parameter edit with a retained request identity through `studio_edit`.
- The system shall retain uncertain outcomes and block resending edits until inspection through `studio_unknown`.
- The system shall reject stale UI responses after app version changes dialog closure or replacement through `studio_scope`.
- The system shall return session inspection close results and a privacy-bounded PDF or JSON report through `studio_history`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: studio_summary
  Given an approved current Hypit source job
  When `studio_summary` opens a session
  Then the exact summary appears before user-confirmed startup
Scenario: studio_fields
  Given compiled text number boolean select color list record and derived fields
  When `studio_fields` renders
  Then every field remains inspectable and supported editable values retain their types
Scenario: studio_edit
  Given a current source head and compiled view
  When `studio_edit` saves one parameter
  Then the exact view source and request identities are sent once
Scenario: studio_unknown
  Given an uncertain effect
  When `studio_unknown` handles the result
  Then inspection is offered and no automatic resend occurs
Scenario: studio_scope
  Given a changed app or closed dialog
  When `studio_scope` receives a late response
  Then the response cannot alter the new interface or app
Scenario: studio_history
  Given a selected owned session
  When `studio_history` inspects closes or exports
  Then observed state is shown without secrets native paths or publication claims
```
