# WizeMe dogfooding: operations with receipts

**Snapshot: November 3, 2026 (UTC).** We are using Wize Marketing Machine on
WizeMe.APP to prove the working marketing loop: connect a real app, collect
evidence, make one approved change, then measure what happened.

| When (UTC) | What we operated | Verified result | Receipt |
| --- | --- | --- | --- |
| Nov 2, 16:44–16:45 | Granted an agent scoped workspace and job reads, then revoked its grant. | Both reads were admitted and revocation was recorded. This does not prove every agent workflow. | E01 |
| Nov 3, 03:59 | Read WizeMe's App Store Connect analytics report inventory using its private connection. | Five selected report families were returned; no report instances or numerical metrics were available. | E01 |
| Nov 3, 04:00 | Ran the first due read after restoring the owner-enabled 24-hour schedule against the current app version. | The worker completed and recorded `WAITING_FOR_REPORTS`. The schedule remains enabled; a later 24-hour refresh is still due. | E01 |
| Nov 3, 03:53 | Checked the deployed Cloudflare OAuth callback relay. | Five synthetic requests passed against the live deployment. This verifies the relay, not a completed Facebook account connection. | E02 |
| Nov 3, 04:26 | Used official OneSignal OAuth and its `list_apps` tool to discover WizeMe. | The intended app was found. Push configuration, SDK registration and device delivery remain unverified. | E03 |

The [redacted receipt index](evidence/wizeme-dogfood-2026-11-03.json) records source
hashes and observation times. Original receipts stay in the owner's private
workspace. They are not publicly downloadable; this is an owner-verifiable
operations record, not an independent audit. No keys or account identifiers are
included.

**What we learned:** WMM can read the real Apple account, dispatch a scheduled
read, preserve missing-data states and record scoped agent access. Changing the
app configuration invalidated the old schedule; a fresh read and owner-confirmed
schedule restored it against the new version.

**Next proof:** collect numerical baseline data; approve and ship one specific
creative or store change; retain its delivery/readback receipt; then report a
dated follow-up with sample sizes and a **continue, stop or revise** decision.
Record elapsed work time against a comparable manual task before claiming time
savings.

No campaign publication, notification delivery, ad spending, measured growth or
time savings is established by this snapshot. OneSignal auto-setup code and
offline tests are engineering evidence, separate from these live operations.

For each new entry, record: **UTC time → action and authority → actual result →
receipt/source hash → next decision**. Append corrections and follow-ups without
rewriting an earlier observation as a later success. Keep failed, empty and
inconclusive results in the record.
