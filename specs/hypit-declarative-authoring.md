# Spec: hypit-declarative-authoring
Status: draft

## MUST - Functional core
### Description
Implement the declarative authoring boundary needed by the integrated Hypit video workflow. Accept a bounded structured scene rather than executable component source. Emit editable Hypit composition, recipe, run and local runtime files using installed built-in packages. No generated JavaScript, shell command, arbitrary package, remote asset or provider endpoint enters the output. This packet does not complete selected-agent orchestration, UI, publication or the wider UPG-07 requirements.

### Requirements (EARS)
- The system shall validate exactly the title, shape and scene fields with 1 through 12 scenes, 1 through 15 integer seconds per scene, total duration at most 60 seconds and 1 through 240 characters of literal text per scene through `scene_contract`.
- The system shall reject unknown fields, unsupported shapes, booleans used as duration, XML control characters and invalid text before emitting exactly the validated source through `scene_validation`.
- The system shall emit escaped literal text into fixed built-in Hypit typography and timeline declarations at 24 frames per second with explicit scene windows and portrait 720 by 1280 or landscape 1280 by 720 pixels through `source_emission`.
- The system shall emit exactly five editable project files with a marked package manifest, composition, style recipe, run target and local-only runtime profile through `project_boundary`.
- The system shall store a canonical scene hash, exact source-file hashes and total duration of at most 60 seconds as reproducible authoring provenance through `authoring_receipt`.
- The system shall reject executable code and remote-provider configuration as scene fields while storing literal markup-looking text only as displayed text through `code_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: scene_contract
  Given a bounded structured scene
  When `scene_contract` is validated
  Then exact declared content and timing are retained
Scenario: scene_validation
  Given malformed scenes and boundary violations
  When `scene_validation` is applied
  Then no source files are returned
Scenario: source_emission
  Given literal text containing markup syntax
  When `source_emission` is applied
  Then parsed source contains literal text and only fixed component declarations
Scenario: project_boundary
  Given a valid composition
  When `project_boundary` is emitted
  Then installed Hypit accepts the project using only the local rendering profile
Scenario: authoring_receipt
  Given identical scene inputs
  When `authoring_receipt` is generated
  Then canonical content and source hashes are identical
Scenario: code_boundary
  Given arbitrary package, code or endpoint fields
  When `code_boundary` is applied
  Then the request is rejected before source emission
```

## SHOULD - Technical
- The output is a pure in-memory file map; job-owned code will write it to a private project directory later. Keep font bytes as separately staged local `font.ttf` input.
- Installed Hypit code is user-managed. This generator redistributes no Hypit source. Do not describe a subprocess as a sandbox.
- Initial text scenes prove compilation and local rasterization; approved product-media, audio, arbitrary component isolation, variants, grants, UI and reports remain required in the parent plan.
- Verify actual installed CLI check/plan/build and decode output under an isolated synthetic probe. No paid generation, account connection or publication.

## Authorized parameters
MAX_SCENES = 12
MAX_TEXT = 240
MAX_SECONDS = 60
FPS = 24
SHAPES = {"PORTRAIT": [720, 1280], "LANDSCAPE": [1280, 720]}
