# Apple Ads campaign acquisition evidence

For a successful Apple Ads Platform campaign report, WMM retains acquisition
cost for each app-owned campaign separately. The provider must return spend
and first-time downloads in the same UTC campaign row. Total installs,
redownloads, first opens and paid subscriptions remain distinct. The retained
cost is an observation from Apple and can change if Apple restates the report.

The receipt records the app, App Store identity, ad account, campaign,
provider source hash, observation time, exact inclusive-start/exclusive-end
window, billing currency, exact spend in minor units and the reported
first-time downloads. Cost per new download is shown in minor units to four
decimal places. Incomplete or open windows, missing rows, missing metrics
and a zero denominator produce no ratio. No campaigns are combined or created.

This is a retained read result. It does not match revenue or user events,
measure incremental growth, authorize activation, or verify protective pause.
The existing Jobs result and its report export retain the same evidence.

