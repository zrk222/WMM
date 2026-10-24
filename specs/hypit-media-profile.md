# Spec: hypit-media-profile
Status: draft

## MUST - Functional core
### Description
Validate real Hypit MP4 artifacts under a dedicated local media profile. Preserve the existing native silent-video validator. This is required for integrated Hypit preview/download and artifact persistence; it does not itself implement those routes or jobs.

### Requirements (EARS)
- The system shall accept exactly one H.264 yuv420p video stream at 24 frames per second with selected portrait 720 by 1280 or landscape 1280 by 720 dimensions and expected duration from 1 through 60 seconds through `video_profile`.
- The system shall accept zero or one AAC audio stream at 48000 samples per second with one or two channels and reject every additional or unsupported stream through `audio_profile`.
- The system shall reject artifacts larger than 67108864 bytes, empty files, mismatched dimensions, timing differences greater than 0.15 seconds and malformed decoder output through `artifact_validation`.
- The system shall return exactly the observed byte count, SHA256 and normalized decoded metadata while preserving the existing native silent-video rejection of audio through `separate_profiles`.
- The system shall invoke a fixed local FFprobe argv with file and pipe protocols only, no shell, no inherited stdin, a 15 second deadline and closed error messages through `decoder_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: video_profile
  Given a real generated synthetic MP4
  When `video_profile` is validated
  Then actual dimensions, timing, pixel format and frame count match the requested profile
Scenario: audio_profile
  Given synthetic MP4s with and without AAC audio
  When `audio_profile` is validated
  Then both supported forms pass and unsupported or extra streams are rejected
Scenario: artifact_validation
  Given malformed bytes and mismatched profile metadata
  When `artifact_validation` is applied
  Then invalid artifacts produce no accepted receipt
Scenario: separate_profiles
  Given the same real MP4 containing AAC audio
  When `separate_profiles` are exercised
  Then Hypit accepts the supported media and the native silent validator still rejects audio
Scenario: decoder_boundary
  Given a failed or timed-out decoder
  When `decoder_boundary` is exercised
  Then the invocation remains local and error output excludes raw decoder content
```

## SHOULD - Technical
- Use the existing shape constants. Never accept filenames or command fragments as FFprobe options; resolve one caller-owned artifact path and keep service admission separate.
- Report observed output format and audio; an audio stream is not proof of narration or music rights.
- Bind accepted artifact hashes to the owning project/job in the later integration. No publication or human approval follows from successful decoding.
- Tests use generated synthetic temporary media; never commit operational video files.

## Authorized parameters
MAX_BYTES = 67108864
TIMEOUT_SECONDS = 15
MAX_SECONDS = 60
TIMING_TOLERANCE = 0.15
FPS = 24
AUDIO_RATE = 48000
timeout = 30
