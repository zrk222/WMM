# Marketing review and shipped-feature mini-demos

These additions keep public claims tied to current product sources and make checking effort visible. They do not start marketing actions automatically.

## Public claims

New verified Page posts retain their exact approved text and source snapshot. Organic publication receipts retain caption lineage, but adapters that do not return a public URL remain explicitly marked as missing that URL. Index an older post, external listing or offer with `marketing-review.index-artifact` through a current owner session or an independently reviewed exact scoped-agent request. Supply its owned campaign scope, a stable UUID, public URL, exact approved wording, source claim IDs and publication timestamp. Owner-entered records remain owner-reported.

Capture the existing private campaign report to see stale wording, links and recorded checking effort. A source hash change flags review only. The report neither fetches public pages nor changes them. Use `marketing-review.check-artifact` for an explicit bounded public text read. This may be unverifiable for rendered or authenticated pages.

Use `marketing-review.effort` to record completed checks, reviews, minutes, evidence fingerprint and timestamp. Use one stable UUID per actual effort event. Replaying it is safe; changing its contents is rejected. Missing effort is unknown, not zero. Report comparisons use the same review window and show recorded effort, not total cost.

## Feature-to-video loop

1. Record a shipped change with `marketing-review.change`: source claim IDs, shipment evidence fingerprint and shipped timestamp.
2. Read `marketing-review.topics`. Current changes within 30 days are suggestions; stale sources and older changes are shown separately.
3. Prepare a normal current short-video brief with authentic screen assets and captions. Register one observational campaign for that brief and channel, including its collector source ID. The existing study link operation supplies one exact campaign/creative tag.
4. Call `marketing-review.prepare-demo` with the change, exact brief and study hashes, channel, and an explicit hook review: audience, problem, reason to watch, opening end within ten seconds, reviewed=true, exact brief hash. This saves preparation only.
5. Inspect `marketing-review.demo-status`. Follow its existing `hypit.queue` operation for local rendering, using an agent with a current app-scoped grant or a current owner session. No new grant is issued by the plan. Inspect the actual video before approval. The default Hypit scene uses approved brief captions; selected screenshots are retained as capture evidence, not silently imported as publishable footage. Use the existing managed-footage workflow to select approved footage when needed.
6. Prepare and approve publication through the existing channel review. Use the exact rendered artifact and the demo's tagged link. Mini-demo source and hook gates are rechecked at approval/dispatch. Publication still needs exact current owner authority, rights and all existing limits.
7. Pass the saved publication ID to `demo-status` to validate the receipt against rendered bytes, owner, channel and link. Unknown delivery must be reconciled, not replayed.
8. Import landing/registration evidence through the existing observational campaign lane. For a D1-D30 return checkpoint, `marketing-review.retention` accepts up to 500 source events and an explicit coverage receipt from that same collector. Rates stay unknown until the acquisition cohort and the full return day have matured and source counts reconcile.

All operations are fixed in the operation catalog and are unbundled from standing policies. No public post, paid call, capture, rendering or billing effect is implied by local preparation. Preserve private source evidence; no customer data or operational databases belong in Git.

## Verification

Run the focused suites in `tests/test_marketing_review.py`, `tests/test_mini_demo.py`, `tests/test_mini_demo_retention.py`, the existing campaign/report and publication suites, and `node --test tests/campaign_owner_report_ui.test.cjs`. Run migration, integrity, architecture, formatting, type and distribution checks. Synthetic tests establish implementation behavior, not real-channel performance or independent human review.
