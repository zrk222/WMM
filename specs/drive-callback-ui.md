# Spec: drive-callback-ui
Status: implementation; main Drive library and agent controls remain required

## MUST - Functional core
### Requirements (EARS)
- The system shall return a dedicated Drive callback page for the existing drive-prefixed consent state without processing provider credentials in a GET, identified by `drive_callback_page`.
- The system shall store callback credentials only in page memory after removing the URL query, require explicit app selection and owner sign-in when needed, submit the callback once, and display the verified account and selected file IDs before exact packet confirmation, identified by `drive_callback_review`.
- The system shall reject malformed or duplicate state fields and stale responses, preserve uncertain operation outcomes without automatic retries, offer cancellation before account adoption and clear transient sign-in secrets after each submission, identified by `drive_callback_recovery`.
- The system shall return keyboard-operable labels and visible status, errors, focus and return controls at desktop and mobile widths, with existing self-only CSP and no new third-party scripts, identified by `drive_callback_access`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: drive_callback_page
  Given a synthetic Drive consent callback
  When `drive_callback_page` exercises the callback page
  Then explicit account review and rejection boundaries are observed
Scenario: drive_callback_review
  Given a synthetic Drive consent callback
  When `drive_callback_review` exercises the callback page
  Then explicit account review and rejection boundaries are observed
Scenario: drive_callback_recovery
  Given a synthetic Drive consent callback
  When `drive_callback_recovery` exercises the callback page
  Then explicit account review and rejection boundaries are observed
Scenario: drive_callback_access
  Given a synthetic Drive consent callback
  When `drive_callback_access` exercises the callback page
  Then explicit account review and rejection boundaries are observed
```

## WON'T - Out of scope
No live Google request, publication, file import, native credential refresh or autonomous authority is completed by this callback packet.
