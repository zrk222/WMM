# Spec: video-editor-ui
Status: draft

## MUST - Functional core
### Description
Make the shared native-source project and actual edited MP4 workflow available
through the human UI. Preserve the full Hypit/OpenCut/marketer scope in
specs/marketer-tool-parity.md; current controls are not the final feature ceiling.

### Requirements (EARS)
- The system shall return a usable human HTTP project create/open/save flow over the same revisioned editor services used by agents through `editor_human`.
- The system shall store clip timing, role, output, crop, rotation, flip, fit, background and color edits and apply split, move, duplicate, delete, insert, undo, redo and restore through `editor_controls`.
- The system shall queue actual current-revision edited MP4 jobs and return real preview, seeking and download controls with live worker monitoring through `editor_media`.
- The system shall reject stale app/project actions and duplicate pending submissions while preserving unsaved fields on failure through `editor_recovery`.
- The system shall return factual task guidance, current edit metrics, PDF report and settings JSON without credential objects through `editor_report`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: editor_human
  Given a current app-owned native source
  When `editor_human` creates and saves a project
  Then HTTP and agent readback return the same current revision
Scenario: editor_controls
  Given a saved project
  When `editor_controls` changes clips and history
  Then the exact backend timeline and revision history change
Scenario: editor_media
  Given a current saved project
  When `editor_media` renders and previews the result
  Then the actual decoded MP4 and download are available with real worker events
Scenario: editor_recovery
  Given a pending or stale action
  When `editor_recovery` receives a duplicate click or changed app
  Then no duplicate write or foreign response is presented
Scenario: editor_report
  Given saved edit and artifact history
  When `editor_report` exports PDF and settings
  Then current observed metrics and project settings agree with server readback
```

## SHOULD - UX and boundaries
Use the existing Research page and shared modal, native labels/buttons/details,
Nanna mission/input/output/next guidance and current app styles. Put trim/time,
framing and color in separate groups. Time fields are explicit source frames at
24fps. Whole-project save uses the same typed service as agents; clip/history
actions use their existing typed endpoints. Unsaved fields must be saved before
commands/render; explain this in-place rather than silently discard them.
Show currently supported silent native source profile. Full audio, rich captions,
overlays, keyframes/masks and complete Hypit controls remain required parent work.
No inert control, automatic publishing, external generation or cost assumption.

Capture app/version and modal generation; reject late responses after close or
switch. One pending command per dialog. Failed writes retain inputs and explain
reloading source/current revision before retrying. Results fetch on explicit
refresh; existing lightweight worker telemetry provides ongoing live progress.
Reports use saved project/source hashes, clip/frame counts, actual artifact/job
status and known0 model API charge with unmeasured machine cost. Settings JSON
is labelled settings only, not a portable media bundle or all-KPI export.
Preview uses exact app-owned artifact routes and real browser video controls.

## Authorized parameters
FPS = 24
MAX_CLIPS = 24
timeout = 15
