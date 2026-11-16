# Apple download measurement in campaign approval

For an organic Facebook Page campaign, the owner can use the exact campaign
link generated in App Store Connect. When a measurement plan is included,
WMM supports one post, zero media spend, and Apple's first-time download count
as the primary metric. The exact link and measurement window, hypothesis and
decision rule remain pinned by the existing approval hash. WMM rejects a link
for another listing and reusing a tracking tag from an earlier campaign.

Before dispatch, the existing evidence check requires a complete App Downloads
Detailed inventory for the current app and connection, observed within seven
days. The matching key must still be available. An empty inventory can indicate
that Apple has not generated report files; the guard establishes readiness to
observe, never a download count. Cancellation, scope expiry and all publication
controls are unchanged. Paid and website measurement rules are unchanged.

Use **Apple analytics → Measure App Store campaign downloads** to collect and
review the approved link's reported counts. Counts are not website first opens,
paid conversions, retention, or causal lift. A first-party product/billing
receipt cannot be attached as the outcome of this plan.
