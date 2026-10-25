# Media discovery, intake and revision workflow
Status: approved goal scope; implementation pending

The user explicitly requires local upload and optional Google Drive access in WMM
UI, viral video selection, creative revisions before Hypit execution and autonomous
mode. This extends the original goal; it does not activate an external account.

## Required end-to-end workflow
1. Choose manual or autonomous operation for the selected app and campaign purpose.
2. Search supported permitted TikTok/Instagram/Facebook sources from a visible WMM
   control. Qualify at least100,000 views AND10 times a documented creator baseline.
   Unknown baseline, unsupported access or stale observations cannot qualify.
3. Select a source, inspect its original URL, observed metrics, source history and
   adaptation rights. Keep selection, data access and permission to reuse separate.
4. Upload local video/image/audio or optionally connect Drive and select media.
   Preserve original bytes, hashes, metadata and provenance in app-owned storage.
   Connection is optional and revocable, with tested scope and clear selected files.
5. Audit media and revise hook, narrative, scenes, captions, timing, crop/aspect,
   CTA, audio and brand purpose before execution. Human and agent use the same
   revisioned project and exact preview/diff; preserve original and undo history.
6. Review exact current source/project/resource/cost summary; execute only within
   current human approval or the selected valid standing scope.
7. Render, decode and preview actual video/audio, export usable artifacts and record
   KPI/telemetry/outcome evidence. Import, draft, queue, render and publish are
   separate states; no implicit publication or paid model/provider calls.

## Autonomous mode acceptance
- A UI toggle explains exactly which discovery, selected-file reads, local imports,
  audit, edit and render actions are delegated; credentials and resource access
  must be onboarded/tested before activation.
- Enforce app/source/account bindings, rights evidence, operation/resource/cost
  limits, expiry, revocation and pause/stop. Missing access, unknown viral baseline,
  disputed rights, unknown cost or unsupported action pauses for a concrete repair.
- Show live stage, current activity, progress, elapsed time, outputs and recovery.
  A human can inspect/revise/pause/cancel; changed source/brief invalidates approvals.
- Neither an OAuth grant nor the toggle itself grants public publication, spend or
  access to every Drive file. Keep existing explicit external-effect boundaries.
- Persist retries/checkpoints without duplicate imports or uncertain render sends.
  Complete UI/CLI/MCP and report parity is required.

## Engineering acceptance
Reuse current creative library, evidence/approval store, render jobs and native
media controls. Extend the NATIVE-only source contract with a managed imported
source resolver; do not accept arbitrary host paths or external URLs as local
render sources. Reject bad/oversized media, private-path escapes, duplicate or
ambiguous requests and cross-app access. Preserve audio or clearly require an
explicit silent profile; never silently discard uploaded audio.

Drive selected-file flow must actually authorize and download selected bytes.
Use a reviewed Picker/permission flow or another explicit scope choice, protected
credentials and constrained provider endpoints. Do not weaken the main UI CSP
globally or claim metadata-only access can download content.

Hypit currently uses APPROVED_BRIEF_CAPTIONS and the editor uses native silent
renders. The new intake/profile/preview/render path is required implementation,
not solved by adding a button. Actual local upload and authorized Drive readback,
real decoded output/audio, revoked access, recovery, desktop/mobile controls,
agent parity, source hashes, privacy and applicable CF gates prove completion.

## UGC import and multi-clip stitching - required goal addition
Users can bring UGC videos, clips, stills and audio through local upload or
optional selected Drive imports, and merge selected assets into a production.
User-supplied media does not need the discovery viral cutoff. Sources retain
provenance and reuse rights evidence; file access is separate from reuse rights.

### Shared human and agent controls
- Provide an app-owned library with playable previews and explicit multi-selection.
  Save selected asset IDs, immutable hashes and source kinds in the project;
  never render an entire library implicitly or accept arbitrary host paths.
- Provide a timeline/storyboard for ordering, inserting, removing, replacing,
  duplicating and stitching clips, source in/out trims, split points, speed,
  aspect/resolution/frame rate, crop/fit/reframe, cuts and supported transitions,
  overlays, captions, branding and CTA.
- Preserve original sound unless explicitly muted. Include clip gain, selected
  voiceover/music, offsets, fades and ducking or explicit conflict resolution.
  Reject unsupported controls before execution; never silently discard audio.
- Human UI and CLI/MCP agents modify the same typed, revisioned source selection,
  ordered tracks and settings. Provide readable change summaries, history, undo
  and preview before exact approval or valid delegated execution.
- Stitching means actual temporal assembly into one playable video with selected
  audio and transitions, preview and export. A list of links, attached brief or
  caption-only replacement does not fulfill this requirement.
- Source, selection, order or setting changes invalidate stale previews/approvals.
  Reject invalid ranges, cross-app sources, changed hashes or unsupported media.
  Pause and recover without duplicate render jobs.

### Autonomous stitching
The autonomous UI toggle must enumerate permitted source libraries and delegated
selection/edit/stitch/render actions. Require tested source credentials, current
rights, app/campaign binding, resource/cost limits, expiry and revocation. Show
live import/audit/edit/stitch/render/verify stages, selected clips, current step,
elapsed time, outputs and pause/stop/recovery. Preserve existing publication and
external-effect approval boundaries.

### Proof required before completion
Import two distinct synthetic UGC video clips with audio and an optional still.
Select/reorder them in the UI, trim and set a transition and audio levels, render
and decode the merged output. Verify actual frame ordering, timing, dimensions,
selected sound, preview and export against the saved project revision. Repeat
through agent controls and bounded autonomous mode. Prove stale approval, bad
trim, foreign-app source, changed media, revoked access and cancellation recovery
reject or pause correctly. Cover desktop/mobile and keyboard workflows. Report
source/clip counts, selected/used durations, render latency, failures, retries,
resource/cost observations and export provenance in analytics/PDF/data reports.
These remain REQUIRED_NOT_COMPLETE. Current Studio parameter controls and the
native silent renderer do not fulfill imported-media stitching.
