# WizeMe dogfooding: operations with receipts

**Snapshot: November 6, 2026 (UTC).** We are using Wize Marketing Machine on
WizeMe.APP to prove the working marketing loop: connect a real app, collect
evidence, make one approved change, then measure what happened.

| When (UTC) | What we operated | Verified result | Receipt |
| --- | --- | --- | --- |
| Nov 2, 16:44–16:45 | Granted an agent scoped workspace and job reads, then revoked its grant. | Both reads were admitted and revocation was recorded. This does not prove every agent workflow. | E01 |
| Nov 3, 03:59 | Read WizeMe's App Store Connect analytics report inventory using its private connection. | Five selected report families were returned; no report instances or numerical metrics were available. | E01 |
| Nov 3, 04:00 | Ran the first due read after restoring the owner-enabled 24-hour schedule against the current app version. | The worker completed and recorded `WAITING_FOR_REPORTS`. The schedule remains enabled; a later 24-hour refresh is still due. | E01 |
| Nov 3, 03:53 | Checked the deployed Cloudflare OAuth callback relay. | Five synthetic requests passed against the live deployment. This verifies the relay, not a completed Facebook account connection. | E02 |
| Nov 3, 04:26 | Used official OneSignal OAuth and its `list_apps` tool to discover WizeMe. | The intended app was found. Push configuration, SDK registration and device delivery remain unverified. | E03 |
| Nov 4, 00:30 | Completed official Meta consent, confirmed the WizeMe.APP Page and tested saved access through WMM. | The private connection returned `CONNECTED_READ_TESTED`. The initial-token lifetime parser repair enabled this connection. | E04 |
| Nov 4, 00:50–00:52 | Activated an owner-approved one-post schedule, signed the owner session out and restarted WMM before the due time. | The recovered worker queued the due job. Its finite allowance stopped execution before any publish intent was created. The trial produced no post. | E05 |
| Nov 4, 01:15–01:29 | Ran the separately approved replacement schedule, then restarted WMM and reconciled its saved post ID. | Meta acknowledged one post. The current attachment readback matched the approved message and link, and WMM saved `VERIFIED`. One publish intent remained after restart. | E06 |
| Nov 4, 01:26 | Refreshed the private Apple analytics inventory. | The authorized read succeeded. All five report families still had zero instances and numerical observations remained unavailable. | E07 |
| Nov 4, 01:31 | Ran one bounded background monitor read and generated the private owner report. | The monitor independently returned `VERIFIED`; the report retained its source receipts and missing business measurements. | E08 |
| Nov 4, 06:45 | Refreshed the running WMM process to the merged version, then used the owner API to inspect its installed-agent setup and saved report. | Agent setup returned the current source-runtime launch details without changing grants. The report hash passed, and the same single verified post intent remained after restart. This was saved local evidence, with no fresh Meta or Apple read. | E09 |
| Nov 4, 09:45 | Restored Windows owner sign-in using the OS certificate verifier, then ran an authorized read of the Apple analytics inventory. | The worker read five report families. Apple returned zero report instances and `WAITING_FOR_REPORTS`. The existing schedule stayed in place. | E10 |
| Nov 5, 01:15 | Inspected the private workspace's saved schedule and its two successive due Apple downloads reads. | Jobs queued on Nov 3 and Nov 4 at 13:28 UTC, 24 hours and 0.434 seconds apart. Both completed with `WAITING_FOR_REPORTS`. The latest job matches the enabled 24-hour schedule. Numerical observations remain unavailable. This inspection made no provider request. | E11 |
| Nov 5, 02:25 | Read aggregate activity from WizeMe's production database using the existing connection in its local source checkout. | An explicit read-only transaction returned external-classified user, registration, conversation and retention-event counts for a 30-day window. The primary connection succeeded after the configured failover failed. Counts stay private. Latest observed activity predates the Facebook trial, leaving campaign impact inconclusive. | E12 |
| Nov 6, 04:12–04:14 | Re-read the fixed 24-hour before and after windows in production and checked whether web traffic was present. | Registrations, conversations and retention events showed no recorded change. The post used an untagged link, so campaign attribution remains unavailable. | E13 |

The delivered change can be inspected on the public Page. [Published WizeMe.APP post](https://www.facebook.com/122102679789533699/posts/122102676339533699)

The [redacted receipt index](evidence/wizeme-dogfood-2026-11-03.json) records source
hashes and observation times. Original receipts stay in the owner's private
workspace. They are not publicly downloadable; this is an owner-verifiable
operations record, not an independent audit. No keys or private account identifiers are
included.

**What we learned:** WMM can read the real Apple account, dispatch a scheduled
read, preserve missing-data states and record scoped agent access. Changing the
app configuration invalidated the old schedule; a fresh read and owner-confirmed
schedule restored it against the new version. E11 now verifies a later scheduled
cycle from the persisted jobs. The next read was due Nov 5 at 13:28 UTC when
inspected. Successful worker execution has continued to preserve the provider's
missing-data state.

The live Meta trial exposed two integration defects. Facebook's initial token
response omitted its lifetime, and a later Page read returned different token
bytes for the same verified Page. The repairs retain provider expiry, identity
and permission checks. Verification and repair attempts consumed the first
trial's allowance. The owner separately approved the replacement that delivered
one post. A third repair replaced a deprecated post attachment field so exact
content verification could complete.

The private E12 packet now supplies an aggregate activity baseline with a dated
window and source definitions. Platform split, attributed installs, revenue and
D1/D7/D30 return rates are still unavailable. The read used WizeMe's existing
database connector. Import into the original WMM workspace remains pending
because its recorded data location is currently unavailable.

**Decision — revise tracking.** The 24-hour comparison on each side of post
verification was retrospective. Site traffic was recorded in both windows.
Without a unique campaign tag, a holdout or an install denominator, the result
is inconclusive for campaign impact. The post verification and monitor
observations were 1 minute 57 seconds apart. That interval measures two
recorded system events. The full work cycle and a comparable manual run still
need timing.

**Next proof:** preregister a new organic test with a unique campaign link and
verify that the tag reaches the landing-page and registration records. Freeze
the measurement window, sample requirements and decision rule before launch.
Then collect the follow-up and record a continue, stop or revise decision.

The verified publication proves delivery. Notification delivery, ad spending,
measured growth and time savings remain unproven. OneSignal auto-setup code and
offline tests are engineering evidence, separate from these live operations.

For each new entry, record: **UTC time → action and authority → actual result →
receipt/source hash → next decision**. Append corrections and follow-ups without
rewriting an earlier observation as a later success. Keep failed, empty and
inconclusive results in the record.
