# Approved campaign automation

Use **Connections → Campaign automation** to review exact Facebook Page posts and an optional Meta paid campaign. Personal account credentials stay in the existing protected, app-scoped social connection; they are not shipped with WMM or shared with other users.

1. In Facebook connection setup, select read access, publishing, or publishing plus ad management. Complete official login with the required permissions and select the Page. Existing read-only connections do not silently gain write access.
2. Enter up to 20 exact posts, your app link and the rights/claim evidence. Separate posts with a line containing `---`. Choose the authority expiry. Paid work additionally requires the exact ad account, currency, maximum media commitment, audience countries, billing acknowledgment and ordinary-ad-category attestation.
3. Review every post, its hashes, the destination, resource limits, expiry and budget. The fresh authenticated owner approves the scope. Approval does not send a post or launch an ad.
4. Run the approved workflow in the UI, or give your agent a separately issued grant for the supported `campaign.*` operations. The agent can operate inside that scope without asking again for each approved post. It cannot prepare or activate its own authority.
5. Inspect real-time saved-stage telemetry, durable provider IDs and read-back. Use the scoped PDF report for delivery counts, retained commitments and observed spend. Reconcile uncertain results before creating replacement requests.

## What the first adapter executes

The implemented organic adapter publishes Page text/link posts and checks the exact returned Page, post ID, content and permalink. The paid adapter promotes a verified saved Page post using a finite Meta engagement campaign, Facebook Feed placement, approved countries, lifetime media budget and end time. It creates objects paused, verifies their account, content associations and settings, then activates the ad set, ad and campaign. Provider ad review and effective delivery are separate from configured ACTIVE status. This is not yet a universal social/video uploader, cross-platform publisher, app-install optimization or automatic campaign-scaling engine.

The owner can authorize this bounded workflow; a model recommendation, OAuth permission or manifest cannot authorize spending. Unsupported providers, special ad categories, missing funding/permissions and mismatched accounts or currency stop launch. Your own developer app, platform review, accounts and credentials remain provider requirements.

## Money, recovery and OFF

WMM atomically reserves each campaign's maximum media commitment. It includes retained commitments from other local workspaces using the same ad account/currency when checking a new scope. Paused, expired, revoked and uncertain work does not automatically free that commitment. The ledger covers this WMM database; it cannot govern campaigns created elsewhere or another independent WMM installation. Provider media budgets are distinct from taxes, fees, conversion and the final invoice. Spend reporting can lag.

Every irreversible step retains its request identity and returned object IDs. A lost response is not permission to resend. Live processes retain their per-intent OS lock. After process death, lock-acquired reconciliation can mark the matching abandoned operation UNKNOWN using the exact lease and immutable inputs; it does not replay activation or invent a missing object ID. Legacy pending records without ownership evidence need process/operator inspection.

OFF blocks new scope work and attempts a verified pause of saved paid campaigns. Separate finite safety allowances preserve protective control when ordinary work has exhausted its quota. A current owner can stop the exact saved campaign after app changes or billing-readiness loss, using the unchanged authorized credential and matching provider account. Changed or revoked credentials require reconnection; WMM cannot pause an account it can no longer access. An unconfirmed pause remains explicit. No switch reverses an already delivered post or incurred charge.

Agents should inspect saved status and reconcile within their agreed call/time budget, use a permitted protective pause when configuration drifts, and report missing authority or evidence. Read-only UI telemetry uses the existing local authenticated session rather than repeatedly querying GitHub; mutations retain fresh identity checks.

## Evidence limits

Local tests exercise the actual owner/agent HTTP gates, budgets, locks, failure recovery and UI with synthetic provider responses. They do not establish live Meta entitlement, approval, delivery, billing accuracy or marketing improvement. Native iOS provider onboarding and signed-device behavior require their own acceptance; a shared catalog does not prove every desktop provider setup is available on-device. Growth, installs and sales are measured outcomes, not guarantees.

Implementation compatibility reference: the official [Meta AdsInsights SDK](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adsinsights.py) lists `maximum` as an insights date preset. The spend adapter uses that bounded available-history request; it does not send the unsupported `lifetime` preset or infer an all-time billing total.
