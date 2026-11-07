# Agent access to organic publication

An owner may grant an agent these fixed operations for the selected app:

| Operation | Capability | Boundary |
| --- | --- | --- |
| `publication.list` | Read connected channel summaries, current media, and the grant owner's publication records | App and grant-owner scoped |
| `publication.get` | Read one saved publication review | Exact authority ID; foreign owner records are denied |
| `publication.draft` | Build a draft from owner-connected channel and app media references | Does not approve or publish |
| `publication.prepare` | Save the exact draft as `PREPARED` for owner review | Does not activate the approval |
| `publication.execute` | Enqueue an already approved publication for the existing worker | Requires the current exact approval; enqueue is not publication |

Agent grants cannot include provider preflight, Instagram credential inspection,
approval activation, revocation, reconciliation, credential management, or a
generic provider-write operation. These actions remain on fresh owner routes.
The operation catalog rejects names outside its closed list, including these
owner controls. The generic HTTP/CLI/MCP operation dispatcher uses the same
catalog and owner-grant checks; it does not route agent bearers through the
owner publication HTTP adapter.

The owner approval binds the app and account, destination, exact content and
media hash, rights, privacy/disclosures, due time, expiry, and bounded call
allowance. Agents may not edit that approval or infer permission from a draft.
The worker checks the saved approval and current app, role, connection, rights,
and allowance before effects. A queued job is only a queued job. Provider
acceptance, processing, publication, and independently verified public
visibility are separate states.

If an effect is unknown, the agent must stop and report the saved status. A
fresh owner uses the read-only reconciliation path; unknown mutations are never
replayed. Browser sign-out does not cancel already approved scheduled work.

For viral source selection, require both at least 100,000 observed views and a
documented creator baseline multiple of at least 10x. Missing or stale baseline
evidence means the candidate is not qualified. Submit a direct post link for
each candidate and baseline observation. Use profile or channel links in source
failure reports when collection stops there. Qualification does not grant
reuse rights: preserve the source, evidence, and owner reuse decision before
production. Keep the selected source-driven workflow; do not replace it with an
original-demo or UGC path when the viral criteria fail. Do not claim virality,
installs, revenue, or lift without measured evidence.

Organic posting scope covers Instagram, TikTok, YouTube Shorts, and LinkedIn.
No new paid-media operations are added; paid ads remain within the existing
Facebook scope. Catalog entries describe local agent operations and do not
certify provider eligibility, actual delivery, public visibility, or marketing
outcomes.

## Collect short-video references for Hypit

Open **Research → Find viral ideas for my app** in an owner session. Select Facebook, Instagram, TikTok, and YouTube Shorts or narrow the search to the channels relevant to this app. Choose a grant with `organic-video.claim` and `organic-video.submit`. Give the assigned agent the saved task ID and hash.

The agent reads `domain_contracts.discovery_research.short_video_collector` from the WMM catalog, claims the saved task, and uses its permitted platform access. For each channel, record direct post links, exact URL post IDs or shortcodes, views, observation times, and 10–20 comparable earlier posts from the same creator and format. Retain source hashes and report login, unavailable data, and empty results explicitly. Use the link's shortcode when a provider supplies a different internal ID. Submit through the scoped WMM operation. A partially observed search stays partial, and its qualifying references can still be reviewed individually.

Open a qualifying reference, inspect it and save a research card. Choose **Render a local Hypit video** to prepare or select the current brief. Its original script and source proof can go through local Hypit preflight without a social connection. To edit third-party footage, supply permitted media through the media library and record the owner's separate rights decision. A research link never imports source footage or authorizes publication.
