# Spec: video-edit-projects
Status: draft

## MUST - Functional core
### Description
Provide the shared app-scoped versioned timeline service required by the complete
human/agent editor. Keep complete control/render/UI acceptance in the parent goal.

### Requirements (EARS)
- The system shall create and read exact typed source-bound timeline revisions through `project_state`.
- The system shall reject stale app, project, source and cross-app revisions atomically through `project_conflict`.
- The system shall apply insert, split, trim, duplicate, move and delete through one timeline mutation service through `project_edits`.
- The system shall store original states and return diff, undo, redo, restore and idempotent replay through `project_history`.
- The system shall return the same project revisions through fixed HTTP, CLI and MCP operations without granting renderer or publication authority through `project_clients`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: project_state
  Given a current native artifact with source evidence
  When `project_state` creates a project
  Then its immutable timeline and actual artifact hash are retained
Scenario: project_conflict
  Given concurrent or foreign project edits
  When `project_conflict` attempts a write
  Then exactly one current write succeeds and the other has no effect
Scenario: project_edits
  Given a source-bound timeline
  When `project_edits` splits, trims, moves and duplicates clips
  Then exact source frame ranges and ordering are persisted
Scenario: project_history
  Given saved edit revisions
  When `project_history` undoes, redoes, restores and replays a request
  Then history is retained and a duplicate request creates no extra revision
Scenario: project_clients
  Given a scoped agent and a separate human session
  When `project_clients` read and edit one project
  Then both use the same current revision and foreign or ungranted input is denied
```

## SHOULD - Architecture and limits
Full product acceptance also requires specs/marketer-tool-parity.md, including
the complete Hypit/OpenCut control inventory and user/agent marketer workflows.
This service's initial native source profile must not become the final editor's
feature ceiling or substitute for any of those required tools.
This packet adds durable timeline operations, not a claim of complete editing.
No inert UI controls or simulated preview/render are added. Existing actual native
MP4 outputs are the first supported media sources; every save, undo/redo/restore
revalidates latest source proof and actual bytes. Hypit, imported video/audio,
images/B-roll, rich keyframes, captions, overlays, audio/ducking, effects, safe areas,
variant render/export and complete human controls remain mandatory parent work.
Do not silently drop them or treat stored timeline data as an executed edit.

Timeline timing uses exact 24fps source frames. Each clip includes role, source,
trim range, speed percentage and finite transform/effect values, so the later
render compiler can consume a closed contract. Do not accept arbitrary paths,
URLs, commands, filters or executable code. This profile has no audio controls.
Output profiles are portrait720x1280, landscape1280x720 or square720x720 at24fps.
Store revisions append-only and maintain head/undo/redo in the same SQLite
transaction. Idempotency binds exact input including current expected version;
replay returns its saved revision without rolling the head backwards.
No agent-edit operation constitutes final human artifact approval.
Record the admitted agent/grant identifiers from gateway context, never caller
input, tokens or profile secrets. Local session draft edits record their caller
class and do not pretend to be independently authenticated artifact approval.
The independently reviewed gateway must propagate that same admitted identity
after exact maker/checker approval; ordinary direct dispatch remains denied when
the owner selected a checkpoint. Changed project revisions fail after approval.

## Authorized parameters
MAX_CLIPS = 24
MAX_FRAMES = 1440
MAX_REVISIONS = 200
MAX_PROJECTS = 100
FPS = 24
timeout = 30
PROFILES = 720
PROFILES = 1280
max_workers = 2
