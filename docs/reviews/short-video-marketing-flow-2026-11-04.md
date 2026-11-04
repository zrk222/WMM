# YouTube, Instagram and TikTok marketing review

Reviewed November 4, 2026 with three actual Meta Muse runs and ECC's marketing-campaign and click-path-audit guidance. Codex checked the findings against current source and official documentation. This is a review and implementation backlog, not a publisher release or a measured marketing result.

## Current capability

| Channel | Connection | WMM publishing | Most useful next improvement |
| --- | --- | --- | --- |
| YouTube / Shorts | Planned; no provider in the registry | Not implemented | Selected-channel connection, usable app CTA and durable resumable upload |
| Instagram / Reels | Professional-account identity; basic scope | Not implemented | Dedicated Instagram Login publishing and measurement adapter |
| TikTok | Identity; basic scope | Not implemented | Creator preview/consent journey and durable publication status |

Evidence: `mission_control/social_registry.py`, `social_profiles.py`, `campaign_access.py` and `static/guided-workflow.js`. Saved plans and successful login do not enable publication. Facebook is the existing campaign executor. The YouTube specification is a proposal, not an implemented integration.

## Highest-value channel changes

**Shorts: make attention lead somewhere useful.** Ordinary URLs in Shorts descriptions and comments are not clickable. Approve and test a channel-profile or related-video route to the app before producing the creative. Record the selected route, CTA and destination check in the existing brief. A related-video link needs its own verified configuration; do not assume the upload API sets it. [YouTube link guidance](https://support.google.com/youtube/answer/13748639).

For publishing, add explicit privacy and audience/disclosure choices, a protected resumable session, and reconciliation of processing, visibility and scheduled publication. Never recreate an upload merely because its response was lost. Keep the tested 60-second Hypit profile; longer Shorts need a separately tested profile. Current quota and eligibility must be checked for the actual project, rather than copied from old examples. [Upload API](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert?hl=en), [resumable protocol](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol).

**Instagram: finish one coherent login-to-Reel path.** WMM uses Instagram Login with `instagram_business_basic`. Meta documents a separate publishing permission. Keep that configuration's scopes, token type and host together; do not paste Facebook Login container calls into the existing connection. Add an app-scoped container/publish/status adapter and exact creative approval before exposing Run. Verify current Instagram Login insight fields and account eligibility before promising metrics. [Meta's Instagram Login collection](https://www.postman.com/meta/instagram/folder/1z5vxzu/instagram-api-with-instagram-login).

**TikTok: automate preparation and preserve the required creator decision.** Direct Post needs the appropriate authorized publishing scope and client eligibility. Its required UX includes fresh creator information, editable preview, user-selected privacy without a default, interaction/disclosure controls and express upload consent. A standing WMM switch cannot substitute for that flow. Keep durable upload and final-post identities, distinguish inbox handoff/processing from completed publication, and reconcile uncertainty before retries. [Posting setup](https://developers.tiktok.com/docs/en/content-posting-api-get-started), [required UX](https://developers.tiktok.com/docs/en/content-sharing-guidelines), [status reference](https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status).

## Shared workflow and acceptance

1. **Qualify the reference.** Retain 100,000 views AND 10 times the documented creator median; use at least ten comparable earlier posts, taking at most the latest twenty. Preserve observation dates, source identities, metric definitions and unknown baselines. YouTube needs explicit qualifier support and compatible view definitions. A reported-count pass is not an independently verified collection. UGC bypasses performance eligibility only.
2. **Reuse the evidence brief.** Existing briefs already bind claims, owned assets, readiness, store destination and tested routes. Add channel-specific hook, first useful app result and one CTA to that infrastructure. Do not introduce a duplicate briefing engine or require every optional marketing field to create a draft.
3. **Separate reference from footage.** An original recreation can use a reference's observed mechanism while foreign-media reuse remains unauthorized. Actual reused footage, music and likeness need current permission. Preserve app/source/review hashes and current rights before rendering or publication.
4. **Prepare once, publish per destination.** Share cleared assets and editing controls; approve each channel's caption, destination, privacy and account separately. Resume existing intents on interruption. Expired/revoked authority, changed assets and uncertain effects must stop the affected action with a specific repair.
5. **Report the marketing decision.** Show source window, sample size and available platform metrics, then separately sourced clicks, installs, activation and revenue. Missing values stay unknown. A public view counter does not establish conversion, attribution or causal lift.

Acceptance must include a tested mobile CTA journey, actual provider-specific transport and recovery tests, restart without duplicate effects, wrong-account/revoked-authority rejection, and dated live publication/status receipts before calling a channel supported. No live channel writes, account permissions or paid spending were performed by this review.

## Review corrections and provenance

Muse received bounded source excerpts and primary-provider summaries, with shell/write/web tools disabled. Each of the three CLI runs exited zero. Its recommendations are advisory: the source review above corrects its broad claims that briefs were absent and that all reference use requires footage-reuse approval. Exact Instagram insight permissions and metrics remain verification work; no third-party guide substitutes for provider evidence.

Private local review records are retained under `.factory/organic-video-automation/muse/` as `youtube-review-muse.md`, `instagram-review-muse.md` and `tiktok-review-muse.md`, with corresponding input packets and terminal JSONL records. They contain no operational account credentials. The source capability table and pending implementation boundaries are the reviewed result.
