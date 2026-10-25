# Spec: managed-media-stitch
Status: implementation

## MUST - Functional core
### Description
Use owner-reviewed uploaded footage in the existing shared timeline, preserving selected sound and original bytes.

### Requirements (EARS)
- The system shall reject missing stale revoked or changed MANAGED sources and bind current owner review version, source hash and manifest alongside existing NATIVE sources using distinct kind and identity keys through `stitch_sources`.
- The system shall return frame timing on a normalized 24 fps timeline for uploaded and native clips, rejecting slices outside normalized duration and above 60 seconds through `stitch_frames`.
- The system shall return AAC audio for projects selecting RETAIN audio and preserve selected clip sound through trim and speed while muted or silent segments contain silence through `stitch_audio`.
- The system shall store an edited H264 MP4 matching requested shape, frame count, audio selection and ordered clip content for at most 24 clips and 60 seconds through `stitch_output`.
- The system shall return the same saved source selections and editing controls through existing shared project operations for user and scoped agent clients without creating new approval authority through `stitch_parity`.
- The system shall reject revoked sources before queue, during render and before commit and retain original bytes and immutable history with 0 automatic retries through `stitch_recovery`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: stitch_sources
  Given current app-owned media and selected timeline controls
  When `stitch_sources` processes the selected project
  Then the declared behavior is observed and invalid source state is rejected
Scenario: stitch_frames
  Given current app-owned media and selected timeline controls
  When `stitch_frames` processes the selected project
  Then the declared behavior is observed and invalid source state is rejected
Scenario: stitch_audio
  Given current app-owned media and selected timeline controls
  When `stitch_audio` processes the selected project
  Then the declared behavior is observed and invalid source state is rejected
Scenario: stitch_output
  Given current app-owned media and selected timeline controls
  When `stitch_output` processes the selected project
  Then the declared behavior is observed and invalid source state is rejected
Scenario: stitch_parity
  Given current app-owned media and selected timeline controls
  When `stitch_parity` processes the selected project
  Then the declared behavior is observed and invalid source state is rejected
Scenario: stitch_recovery
  Given current app-owned media and selected timeline controls
  When `stitch_recovery` processes the selected project
  Then the declared behavior is observed and invalid source state is rejected
```

## WON'T - Out of scope
No provider generation, Drive access, publication or spending. Uploaded originals remain immutable. Owner reuse attestations are not independent legal verification. Preserve old silent-native project bytes and source bindings. New source selections require current approval; no agent self-approval.

## Data model
MANAGED source fields remain kind, id and sha256; IDs follow the actual managed-media generated identity format. Bind exact review version and app manifest. Source caches and copies key by kind and id. Existing native bindings remain byte-compatible. Optional clip audio is RETAIN or MUTE; omission preserves legacy silent behavior. New uploaded clips default RETAIN in UI, while native silent clips remain silent. Normalize picture to 24 fps before applying source-frame trim; trim audio by matching normalized times and apply the same speed factor. Bound encoder execution to existing 180 seconds and output to 64 MiB. Input decoding remains existing managed-media 64 MiB and 60-second profile. Revocation and owner-role invalidation revalidate through the same DB snapshot used by queue and commit. Copy verified bytes into generated private filenames without reopening a user path after verification.
