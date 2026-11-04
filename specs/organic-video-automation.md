# Spec: organic-video-automation
Status: draft

## MUST - Functional core
### Description
An owner can run a bounded WizeMe promotion workflow that discovers relevant social-video references, qualifies their documented performance, uses an evidence card to prepare an original app campaign, adds app-owned demo footage, renders through Hypit, and publishes an approved Facebook Page Reel with monitoring and reporting. Organic mode is the default. The owner may select a separately authorized paid path. Discovery, capture, rendering, publication, provider processing and outcomes remain distinct.

### User roles
- An authenticated owner selects the Page, source authority, publication policy, expiry and limits and can revoke authority.
- A scoped agent prepares and executes only operations admitted by the retained owner policy; it cannot create owner approval.
- The worker resumes safe local work and reconciles provider effects without silently repeating an uncertain mutation.

### Requirements (EARS)
- When a workflow starts, the system shall create a hash-bound task for an authorized external personal agent to collect videos relevant to the selected genre and app type through `source_discovery`.
- When a scoped personal agent claims a discovery task, the system shall record the claim identity and accept only an exact task-bound observation bundle through `collector_submission`.
- When qualifying a non-UGC reference, the system shall validate documented views of at least 100000 and at least 10 times the documented creator baseline from at least 10 comparable prior posts through `viral_qualification`.
- If source relevance, view count, creator baseline or collection evidence is unknown, the system shall retain the item as a candidate without claiming research qualification through `candidate_only`.
- If foreign source reuse rights are unknown, the system shall block LICENSED_EDIT and foreign-byte reuse while allowing original recreation of a research-qualified mechanism through `foreign_rights`.
- Where owner-authorized UGC is selected, the system shall allow exemption from viral thresholds while validating current rights and relevant app context through `ugc_eligibility`.
- When preparing a campaign, the system shall store the selected discovery evidence card, brief, original app claims and allowed footage in the editor and Hypit workflow through `evidence_to_brief`.
- The system shall default to organic Reel mode with zero ad budget, zero ad-account binding and no ad calls through `organic_default`.
- When the owner explicitly selects paid mode, the system shall validate separate current paid scope, billing acknowledgment, account, currency, targeting and commitment limits with a maximum scope expiry of 24 hours through `paid_selection`.
- When capture is requested, the system shall record only an owner-selected WizeMe app-owned demo source with no personal account or customer data through `demo_capture`.
- When footage is registered, the system shall store its app, immutable media ID, SHA-256, provenance and current owner rights review through `managed_source`.
- When Hypit is asked to render footage, the system shall consume only current owner-allowed app-owned managed-media bytes by ID and hash through `hypit_footage`.
- If source bytes, app scope, owner rights or current manifest change before or during rendering, the system shall stop or reject the render through `source_revocation`.
- When a render succeeds, the system shall save the actual MP4 artifact hash, source identities, authoring hash, renderer identity and job receipt through `artifact_provenance`.
- The system shall store an agent manifest and owner interface binding exact final content or an explicit standing generated-content policy to the selected Page, source rights, claims and quotas with at most 20 posts through `owner_policy`.
- When a standing generated-content policy admits an output, the system shall validate its allowed sources, factual claims, generation cost and at most 20 post quotas and save an immutable output admission bound to that policy and artifact hash through `generated_admission`.
- If generation claims, rights, model-provider charges or output identity cannot be verified against the policy, the system shall block publication and request owner review through `admission_block`.
- When publishing an admitted Reel, the system shall store the app, Page, caption, source rights, policy, final artifact SHA-256 and request identity through `video_binding`.
- When a provider mutation is sent, the system shall save a durable stage identity before dispatch and retain the returned provider video ID before upload or publication through `stage_receipts`.
- If create, upload or publish has an uncertain outcome, the system shall preserve UNKNOWN and block automatic mutation replay until supported readback resolves it through `unknown_recovery`.
- When uploading media, the system shall send verified local bytes to the exact pinned Meta upload host with no provider-supplied arbitrary URL through `pinned_upload`.
- When Meta reports processing or publication, the system shall return acknowledged, processing, published, verified and unknown states using exact owned provider identity through `provider_readback`.
- When an active schedule reaches its due time, the system shall validate policy, source rights, exact output, Page, expiry and remaining quota before each effect through `scheduled_recheck`.
- When the owner revokes the policy or switches a schedule OFF, the system shall block future admissions and cancel unclaimed jobs without claiming to undo dispatched effects through `stop_control`.
- The system shall preserve existing text and link post contracts and receipts through `text_compatibility`.
- The system shall display preparation, cost, provider processing and publication evidence without claiming remote bytes match the local hash or inventing reach, installs or revenue through `honest_report`.
- When a published Reel has a provider readback, the system shall display observed monitoring and report values with source and observation time through `outcome_monitoring`.
- When an owner activates a schedule with explicit phase-observation limits, the system shall continue only acknowledged processing stages through the existing worker within current policy, call and observation limits through `bounded_observation`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: source_discovery
  Given an AI life coach app and personal growth genre
  When `source_discovery` prepares an authorized external-agent task
  Then the task binds the permitted sources, app, genre, expiry and read limits
Scenario: collector_submission
  Given a claimed task and a submitted observation bundle for a different task
  When `collector_submission` checks the bundle
  Then the bundle is rejected without marking live collection complete
Scenario: viral_qualification
  Given a non-UGC reference with 100000 documented views and a 10000-view median from 10 documented comparable prior posts
  When `viral_qualification` evaluates the two values
  Then the reference meets both performance thresholds
Scenario: candidate_only
  Given a reference with no documented creator baseline
  When `candidate_only` evaluates the evidence
  Then the reference remains a candidate and its footage is not admitted for reuse
Scenario: foreign_rights
  Given a research-qualified reference with unknown foreign-footage rights
  When `foreign_rights` evaluates a requested original recreation
  Then the original app brief is allowed and foreign footage remains blocked
Scenario: ugc_eligibility
  Given relevant owner-authorized UGC with current rights and fewer than 100000 views
  When `ugc_eligibility` evaluates the reference
  Then viral performance thresholds do not block it
Scenario: evidence_to_brief
  Given a qualified reference and current app evidence
  When `evidence_to_brief` prepares an original campaign
  Then the saved brief binds the discovery evidence card and does not copy unlicensed source footage
Scenario: organic_default
  Given a new workflow without paid selection
  When `organic_default` prepares the request
  Then the ad budget is zero and no ad account or ad mutation is used
Scenario: paid_selection
  Given the owner selects paid mode without approved billing limits
  When `paid_selection` checks authority
  Then no paid effect is admitted
Scenario: demo_capture
  Given a personal account or customer dataset
  When `demo_capture` checks a capture source
  Then the capture is rejected
Scenario: managed_source
  Given a managed footage item with a changed digest
  When `managed_source` checks its source binding
  Then the footage is rejected
Scenario: hypit_footage
  Given current allowed app-owned footage
  When `hypit_footage` renders its selected frames
  Then the output includes those frames and retains the source hash
Scenario: source_revocation
  Given an owner revokes source reuse during a render
  When `source_revocation` checks the render guard
  Then the worker stops without committing an authorized artifact
Scenario: artifact_provenance
  Given a successful Hypit video render
  When `artifact_provenance` commits the artifact
  Then the saved receipt binds the output hash to source and authoring identities
Scenario: owner_policy
  Given an agent proposes future generated posts
  When `owner_policy` checks authorization
  Then only a current owner-approved exact or bounded standing policy can admit publication
Scenario: generated_admission
  Given a valid standing generated-content policy and matching output
  When `generated_admission` evaluates the output
  Then one durable admission binds the policy and exact artifact hash
Scenario: admission_block
  Given a generated output with an unverified claim or unknown model cost
  When `admission_block` evaluates the output
  Then publication is blocked for owner review
Scenario: video_binding
  Given an approved Reel and changed caption or video bytes
  When `video_binding` checks the request
  Then the changed request is rejected
Scenario: stage_receipts
  Given an acknowledged provider create step
  When `stage_receipts` prepares the upload
  Then the exact provider video ID is durably saved first
Scenario: unknown_recovery
  Given a timeout after a provider mutation
  When `unknown_recovery` restarts the worker
  Then no new create, upload or publish mutation is dispatched automatically
Scenario: pinned_upload
  Given an upload URL outside the fixed Meta host and path
  When `pinned_upload` validates the destination
  Then no credential or video byte is sent there
Scenario: provider_readback
  Given a provider video ID still processing
  When `provider_readback` reads its status
  Then the result remains processing rather than verified publication
Scenario: scheduled_recheck
  Given an approved Reel whose source rights are revoked before its due time
  When `scheduled_recheck` evaluates the effect boundary
  Then no provider mutation is admitted
Scenario: stop_control
  Given a schedule with queued and already dispatched work
  When `stop_control` switches it OFF
  Then queued work is cancelled and dispatched outcomes remain separately recorded
Scenario: text_compatibility
  Given an existing approved text and link post
  When `text_compatibility` validates the legacy request
  Then the original canonical hash and receipt remain readable
Scenario: honest_report
  Given a local artifact hash and an acknowledged upload
  When `honest_report` displays the receipt
  Then it does not claim remote byte equality or measured business outcomes
Scenario: outcome_monitoring
  Given a supported provider observation with its timestamp
  When `outcome_monitoring` reads the saved report
  Then it shows the observed value and source without inventing business outcomes
Scenario: bounded_observation
  Given a current approved schedule with thirty-second intervals and a twelve-follow-up-job ceiling within the reserved call allowance
  When `bounded_observation` sees a successful worker return an acknowledged processing stage
  Then a separately retained next observation queues one existing worker job, preserving history and the original approved due time, while unknown or interrupted mutations require owner recovery
```

## SHOULD - Technical and structural
- Facebook target is a Page Reel, not a generic Page feed-video claim. Confirm Graph API v26 behavior, current permissions, supported media limits and Page identity before any live effect. Use documented create, local binary upload, status and publish stages; a provider acknowledgment alone is not verified publication.
- Reuse existing discovery source collections, discovery evidence cards, creative analysis and original briefs, managed-media ownership and rights review, Hypit render receipts, campaign authority, scoped agent grants, durable worker jobs, monitoring and schedule OFF controls. The collection is a destination for retained observations, not a live source. Begin by preparing a durable task for an external PERSONAL_AGENT through its owner-scoped gateway; the external agent must claim it, conduct authorized internet reads using its own tools and submit task-bound observations. The agent may use a separately owner-authorized platform browser or account capability or permitted API, limited to public-post metadata; do not capture private messages or other users' private material. Existing tool-free internal drafting agents remain unchanged. Never infer web capability, browser access, account authentication or cookie inheritance from a WMM grant. A disconnected agent, login wall, CAPTCHA, timeout or absent submission yields INCOMPLETE and named missing evidence; a saved pool cannot replace a live run. Do not add arbitrary scraping. A new commercial or free connector is optional, not mandatory.
- Discovery records the source URL and identity, selected genre and app type, observation timestamps, view evidence and creator baseline method, underlying evidence and computed ratio. Apply existing `viral_policy.qualify` unchanged: select up to the 20 newest comparable prior posts from the same creator, platform and format, excluding the candidate, with at least 10 individually documented view counts. Use the exact rational median of all selected rows as the positive baseline. Source observations must be no older than 24 hours when qualifying; future timestamps are invalid. Require at least 100000 views and views >= 10 * baseline; unknown, expired or unverifiable performance observations remain candidate-only and the workflow reports missing baseline evidence. Reported-count qualification permits reference inspiration only after relevance and collection review and never grants footage reuse. ORIGINAL_RECREATION is the default and uses original script, footage and audio; unknown foreign rights block LICENSED_EDIT and foreign bytes, not inspiration. All final production assets require current ALLOWED rights. Never use an undocumented third-party multiplier as qualification. Current discovery qualification covers TikTok, Facebook and Instagram; YouTube is unsupported until its own source and qualification contract exists. UGC is exempt only from performance thresholds, not from relevance, provenance or rights requirements.
- Capture runs in an isolated demo session and must never use the owner's current browser session, real accounts or personal data. The owner may select the provided local WizeMe manual promo MP4 as app-owned supporting material through managed-media intake and current owner rights review; its existence alone is not a rights approval.
- Keep existing Hypit text scenes unchanged. Add a versioned footage segment using the existing studio shape `{id, sha256, in_frame, audio}` and the scene's integer seconds at 24 normalized frames per second; reject paths, URLs and code. The first profile supports `MUTE`; reject `RETAIN` until the audio path is proved. At claim, verify app and current source rights and copy a hash-verified private snapshot. Cut exactly from `in_frame` for the scene duration, then recheck rights and hash immediately before commit; discard output if the guard fails. Validate the selected Reel geometry and duration against this specification before publication.
- The interface must let the owner select an app-owned demo source, capture or import it, attest rights and claims, preview the actual rendered video, choose organic or paid mode, approve exact content or an explicit standing policy, and inspect or stop the workflow. A standing policy must declare allowed source IDs and hashes, source rights, approved claim evidence, model/provider cost ceiling, generation and post counts, selected Page, expiry and revocation behavior. Agent-generated admissions are not owner approvals.
- Prepare content before exact approval. For future generated content, implement a distinct owner-approved policy and deterministic admission checks; unclear or unsupported claims and unverifiable costs require owner review. Do not silently widen existing exact-content scopes.
- Stream a verified private snapshot without a database write transaction spanning network I/O. Pin the Graph and upload hosts separately; validate all IDs, paths, HTTPS certificates and redirects. Persist a per-stage request identity and bounded call counters. Reconcile only operations for which an authoritative readback exists; unknown creation without a remote ID stays blocked.
- Report local artifact integrity separately from Meta processing and Page-visible readback. Provider readback does not prove the original local hash matches transcoded provider bytes. Generation service costs are separate from ad spend and must not be assumed zero.
- Use synthetic fixtures and fake provider transports for automated tests; no personal data, real credentials, external provider writes, or paid effects are used by tests. Full provider acceptance requires separately authorized, current proof.

## Interface contracts
- The discovery task binds task ID, app and current app hash, owner-scoped grant and hash, selected genre and app type, allowed platforms and hosts, query/read/time budgets, expiry, request identity and read-only boundaries. The external agent claims a lease under the grant and returns a submission with the exact task and claim identities, task hash, collected time, per-source failures, candidate plus comparable-history observations in the exact existing `viral_policy.FIELDS` shapes, and sidecar evidence of source URL, retrieval time, observation identity, evidence hashes, relevance and rights status. The gateway validates the active grant, matching app, task hash, lease, scope, expiry, ownership and bounded exact schema before persisting, and rejects stale, foreign, altered or conflicting replay; exact duplicate submission returns the retained receipt. The agent's source assertions are provenance, not independent verification or reuse permission. The existing collection is the sink, and collection completes only after a successful live task-bound submission is retained. A missing or partial bundle remains INCOMPLETE with named failures.
- A capture request selects a pre-registered WizeMe demo target or owner-provided app-owned media ID; it cannot name a filesystem path, personal account, arbitrary URL or recording target. Capture produces a local managed-media item and rights review; the output remains ineligible until owner rights are current.
- A separate organic video policy record has immutable owner principal, app and Page connection IDs, default mode `EXACT` or explicitly selected `STANDING_GENERATED`, allowed source IDs and SHA-256 values, current rights references, exact claim and caption templates with evidence hashes, allowed transformations and generation providers, model-cost ceiling in minor units and currency, generation count ceiling, maximum 20 posts, maximum 500 provider calls and expiry within 24 hours. Paid authority is separate. Only an owner-authenticated local route creates, changes or revokes the policy; an agent may read and validate but never create, modify or revoke it. Existing campaign scopes and their 100-post limit remain unchanged.
- A generated admission stores the policy hash, source references and current rights versions, exact allowed template and evidence hashes, output SHA-256, caption, generation receipt and settled or reserved model cost. Unknown cost, unsupported claims, changed policy, changed bytes, exhausted limits, revoked rights or uncertain paid-generation reservation block admission. Model spend is reserved before any separately authorized billable generation; an uncertain charge remains held for reconciliation.
- A typed Reel request stores app ID, Page ID, policy and admission hashes, source rights hashes, artifact ID and SHA-256, caption and unique request ID. Replay with the same request identity and same input returns the saved intent; changed input is rejected. Legacy text and link request identities and hashes remain unchanged.
- Durable Reel stages are `CREATE_DISPATCHING`, `CREATE_UNKNOWN`, `CREATED`, `UPLOAD_DISPATCHING`, `UPLOAD_UNKNOWN`, `UPLOADED`, `PUBLISH_DISPATCHING`, `PUBLISH_UNKNOWN`, `ACKNOWLEDGED`, `PROCESSING`, `VERIFIED` and `BLOCKED`. Persist dispatch before each mutation and receipt immediately after; a crash in dispatch becomes UNKNOWN. A stage with no authoritative remote readback cannot be automatically retried.
- The transport functions `create(page, metadata, context)`, `upload(video_id, artifact, context)`, `read(video_id, context)` and `publish(video_id, metadata, context)` receive a typed internal context derived from the protected connection, containing private credentials and the live authority guard. The context is never accepted from HTTP or agent JSON and credentials are never stored in content metadata, jobs or receipts.
- Provider publication is `VERIFIED` only after bounded readback establishes the expected Page, saved video identity, published state and matching exposed caption. If Meta does not expose sufficient identity or state, report the strongest observed state and keep verification unconfirmed. Page visibility is a separate observation when supported.

## Authorized parameters
MAX_POSTS = 20
MIN_VIRAL_VIEWS = 100000
MIN_BASELINE_MULTIPLE = 10
MIN_BASELINE_POSTS = 10
MAX_BASELINE_POSTS = 20
MAX_OBSERVATION_AGE_HOURS = 24
MAX_SCOPE_HOURS = 24
MAX_SCENES = 12
MAX_VIDEO_SECONDS = 60
MIN_REEL_SECONDS = 4
MIN_REEL_WIDTH = 540
MIN_REEL_HEIGHT = 960
MIN_REEL_FPS = 23
REEL_ASPECT_WIDTH = 9
REEL_ASPECT_HEIGHT = 16
MAX_CAPTURE_SECONDS = 60
MAX_CAPTURE_ITEMS = 20
MAX_PROVIDER_CALLS = 500
MAX_MEDIA_BYTES = 67108864
ORGANIC_AD_SPEND_MINOR = 0
GRAPH_API_VERSION = 26
VIDEO_PHASE_OBSERVATION_SECONDS = 30
VIDEO_PHASE_FOLLOWUP_JOB_LIMIT = 12

## Non-goals
- No arbitrary web scraping, personal account capture, paid authorization bypass, invented claims, or guaranteed performance outcomes. Facebook Page Reels are the first live connector; other requested social platforms remain future work and are not represented as supported.

## Decision logic (factory candidates)
| # | if | then |
|---|----|------|
| 1 | `organic_default` is selected | Disallow ad account, ad spend and ad mutations |
| 2 | `admission_block` is triggered | Block admission and request owner review |
| 3 | `unknown_recovery` is triggered | Retain UNKNOWN and allow only supported readback |
| 4 | `provider_readback` is processing | Report the processing state without a verified-publication claim |
