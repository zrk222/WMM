# Spec: media-duration
Status: implementation

## MUST - Functional core
### Requirements (EARS)
- The system shall render a selected `duration_boundary` of 1440 frames at24fps with retained AAC audio into a valid MP4 of 60 seconds, preserving all video frames and selected sound while canceling concat mux priming offset.
- The system shall emit fixed internal `duration_mux` arguments for AAC48kHz output with a correction of -0.02133333333 seconds and generated segment filenames, applying the encoder priming correction only when the render profile includes audio and preserving silent-profile behavior.
- The system shall reject imported media beyond 60 seconds and timelines beyond 1440 frames through `duration_limits`, retaining existing size, codec, stream-inventory and source validation without broadening an upload or metadata bound.
- The system shall preserve shared user and agent `duration_workflow` state through existing project revisions, render jobs and artifact receipts, with owner reuse rights and revoked or foreign-source denial and the existing render deadline of 180 seconds unchanged.
- The system shall return actual decoded picture, sound, timing and source-bound hashes through `duration_proof`, covering one full-length clip and a stitched multi-clip60-second timeline, with current render deadline of 180 seconds and probe deadline of 15 seconds retained.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: duration_boundary
  Given an owned full-length video with source audio
  When `duration_boundary` renders its exact selected timeline
  Then all1440 frames and the selected sound remain in a valid60-second artifact
Scenario: duration_mux
  Given fixed generated segment inputs
  When `duration_mux` compiles silent or audio output
  Then only the audio profile receives its fixed priming correction
Scenario: duration_limits
  Given over-limit media or a timeline beyond 1440 frames
  When `duration_limits` validates the input
  Then the unchanged declared bounds reject it
Scenario: duration_workflow
  Given a saved owner-reviewed media project
  When `duration_workflow` queues and completes its render
  Then the exact project revision and source hashes identify the downloadable result
Scenario: duration_proof
  Given actual full-length single and stitched source clips
  When `duration_proof` decodes the output
  Then ordered picture selected sound frame count and timeline duration match the saved project
```

## WON'T - Out of scope
No relaxed media-upload limit, new UI or agent input fields, broader execution permission, provider invocation or publication. This repair does not complete the remaining Drive, full editing or other goal requirements.
