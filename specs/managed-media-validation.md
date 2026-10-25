# Spec: managed-media-validation
Status: implementation packet; full media workflow remains required

## MUST - Functional core
### Description
Validate supplied UGC video bytes before app-owned intake, project source binding
and stitching. This packet implements the technical byte boundary only. It does
not infer ownership, adaptation rights, creative quality or publication approval.

### Requirements (EARS)
- The system shall inspect MP4 MOV or WebM bytes from 1 through 67108864 bytes through `media_bytes`, using generated private filenames and only mov or matroska demuxers with file and pipe protocols; reject other suffixes, empty bytes and larger input before native execution.
- The system shall accept exactly one video stream and zero or one audio stream through `media_metadata`, with integer dimensions from 2 through 4096, at most 8388608 pixels, duration greater than 0 and at most 60 seconds, and frame rate from 1 through 120; audio must have 1 or 2 channels and sample rate from 8000 through 192000.
- The system shall decode every selected picture and audio stream through `media_decode`, retain whether audio exists, reject native failure or zero decoded video frames, and return input SHA256 and decoded evidence without returning native paths or raw diagnostics; probing is limited to 15 seconds and decoding to 180 seconds using the existing 1048576-byte output cap and agent_process.capture cleanup.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: media_bytes
  Given supported input with a path-like original filename
  When `media_bytes` stages the supplied bytes
  Then only a generated private filename is used
  And empty oversized or unsupported inputs reject before native execution
Scenario: media_metadata
  Given video metadata with two audio streams or nonfinite timing
  When `media_metadata` checks the actual stream selection
  Then the ambiguous or invalid input rejects
Scenario: media_decode
  Given actual synthetic video with audible source audio
  When `media_decode` inspects and decodes it
  Then audio remains present in returned metadata and original bytes remain unchanged
  And a failed or empty decode cannot become accepted media
```

## SHOULD - Engineering and integration
- Reuse `agent_process.capture` for bounded process ownership and cleanup.
- Tests use isolated synthetic bytes and installed native tools; distinguish mock
  metadata tests from actual native decode proof. Do not install dependencies.
- The caller must separately bind app, source provenance, current rights review,
  exact immutable bytes and approval before assembly or execution.

## WON'T - Completion boundary for this packet
- No upload endpoint, managed media persistence, Drive connection, source rights
  grant, user selection, stitching UI, audio mixer or Hypit authoring is implemented
  by byte validation. These remain required subsequent integration work.
- No native-process OS isolation, measured resource cost or production acceptance
  is claimed from timeout/output bounds or synthetic fixtures.
