# Checklist owner UI packet

Requirement T5 R2/R6: add one Inspect production gaps action to a saved SHOTS
revision in the existing packaging modal. Reuse same-origin packaging.checklist,
current app/principal lifecycle, status/error announcements and shared reports.
Reject receipts with mismatched app, manifest or exact shot identity/hash.
Display source freshness, each script/shot/media/claim gap and editing decisions;
explain the next action without labeling a checklist as production readiness.
PDF print view, JSON and CSV must include checklist identity and gaps with unknown
sales and no invented execution. No render/job/approval buttons added by this
packet. Actual editor/Hypit handoff remains required in later T5 tasks.

Ownership: packaging-model.js, packaging-ui.js, ui-stories.js and their focused
Node tests. Existing shared report/CSS controls are reused. Validate malformed
receipts, XSS/CSV injection, stale/foreign contexts, late responses and reports;
actual desktop/mobile browser check and Prestige audits precede completion.
