# Spec: video-edit-render
Status: draft

## MUST - Functional core
### Description
Execute current shared timeline edits as actual validated MP4 output; retain full
Hypit/OpenCut and marketer requirements from specs/marketer-tool-parity.md.

### Requirements (EARS)
- The system shall render exact ordered source-frame slices, speed, crop, fit, rotation, flips, background and color adjustments into actual edited video through `edit_output`.
- The system shall reject stale project revisions, source bytes or rights before queue and artifact commit through `edit_proof`.
- The system shall store idempotent cancellable edit jobs and durable hash-bound artifacts with actual step telemetry through `edit_jobs`.
- The system shall return the same render job/history through human HTTP and fixed CLI/MCP operations, with exact preview/download seeking through `edit_clients`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: edit_output
  Given real synthetic native source video
  When `edit_output` renders different current timeline controls
  Then decoded output frames, dimensions and duration match the requested edit
Scenario: edit_proof
  Given a source or project changed during rendering
  When `edit_proof` checks artifact commit
  Then no accepted MP4 is saved
Scenario: edit_jobs
  Given repeated and cancelled render requests
  When `edit_jobs` dispatches the saved worker
  Then one saved job is reused and cancelled work commits no artifact
Scenario: edit_clients
  Given scoped human and agent requests
  When `edit_clients` queue and inspect the output
  Then exact job/artifact identities match and foreign access is rejected
```

## SHOULD - Architecture and boundaries
Compile only the already-closed timeline contract into internal FFmpeg argv and
filters. Never accept source paths, filter expressions, shell strings or URLs.
Copy selected verified MP4s into a private job attempt folder; check hashes after
copying. Each clip produces exact frame-count H264/yuv420p24fps. Concatenate only
fixed internal segment filenames. Validate final codec, fps, dimensions, duration,
byte bound and digest. Output is currently silent because native source profile
contains no audio; audio, full Hypit sources, rich overlays/captions/keyframes,
full human editor and marketer scope remain mandatory. Never report an unsupported
control as rendered. Initial fixed color controls use explicit bounded values.

Queue freezes id/revision/hash plus full source-bound project data; every worker
and commit rechecks current head and proof, ownership and standing scope. An edit
after queuing makes that render stale. Cancel terminates only the owned child and
removes temporary or exclusively created uncommitted output. Artifact readback
separates retained original version from current project status; withdrawals of
source rights or changed media deny preview/download. Local encode adds no model
API charge; machine cost is not measured. Final human review remains required.

## Authorized parameters
FPS = 24
MAX_BYTES = 8388608
RENDER_SECONDS = 180
timeout = 30
