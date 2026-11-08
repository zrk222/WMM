# Spec: keyboard-review

Status: draft

## MUST - Functional core
### Description
Make repeated review dialogs operable with the keyboard alone without implicit
approval. Opening a dialog moves focus inside it, Tab and Shift+Tab stay within
its visible controls, Escape closes it without submitting, and closing returns
focus to the control that opened it.

### Requirements (EARS)
- When a dialog opens, the system shall focus its first visible focusable control through `modal_focus`.
- While a dialog is open, the system shall keep Tab and Shift+Tab within its visible focusable controls through `modal_trap`.
- When Escape is pressed in an open dialog, the system shall close the dialog without submitting a form or creating approval through `modal_escape`.
- When a dialog closes, the system shall return focus to the connected control that opened it, or leave no implicit focus target through `modal_return`.
- The system shall not activate approval, submission or provider effects from focus movement, Escape or closing.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: modal_focus_trap
  Given a review dialog opened with the keyboard
  When the operator presses Tab or Shift+Tab repeatedly
  Then focus stays within the dialog controls
Scenario: modal_escape_no_approval
  Given an open review dialog with a submit control
  When the operator presses Escape
  Then the dialog closes without submitting
  And no approval or provider effect is recorded
Scenario: modal_return
  Given a dialog opened from a control
  When the dialog closes
  Then focus returns to that control when it is still connected
```
