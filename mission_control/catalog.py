"""Twelve stages, user-facing evidence forms and provider capabilities."""
STAGES = [
    (1, "Register your app", "Plan", [], "Confirm the job, audience and exact release.", ["manifest"]),
    (2, "Prove the core journey", "Plan", [1], "Attach current build and device test evidence.", ["readiness"]),
    (3, "Connect measurement", "Plan", [1], "Document attribution, consent and payment reconciliation.", ["measurement"]),
    (4, "Understand the economics", "Plan", [3], "Calculate mature conversion and contribution.", ["cohort"]),
    (5, "Prepare your store page", "Launch", [1,2], "Match verified claims to authentic store assets.", ["claim","asset","store"]),
    (6, "Build the creative test", "Launch", [5], "Prepare six briefs from one proven user job.", ["experiment"]),
    (7, "Prepare distribution", "Launch", [4,6], "Review intent, destination, limits and handoff.", ["distribution"]),
    (8, "Deliver the first value", "Launch", [2,3], "Verify install and sign-in route continuity.", ["route"]),
    (9, "Verify conversion", "Learn", [3,8], "Check price, trial, restore and localized checkout.", ["billing"]),
    (10, "Measure retained value", "Learn", [4,8], "Use the app's value cadence, not generic daily opens.", ["retention"]),
    (11, "Evaluate the experiment", "Learn", [7,9,10], "Review mature outcomes, uncertainty and costs.", ["evaluation"]),
    (12, "Reflect and improve", "Learn", [11], "Propose one versioned change with a rollback.", ["learning"]),
]

FIELDS = {
    "readiness": ["release", "result", "device", "checked_at", "p0_count"],
    "measurement": ["release", "result", "attribution_method", "consent_review", "refund_reconciliation"],
    "claim": ["release", "claim", "result", "locale", "checked_at"],
    "asset": ["release", "filename", "sha256", "device", "locale", "authentic", "rights_cleared"],
    "store": ["release", "locale", "destination", "availability", "checked_at"],
    "experiment": ["hypothesis", "primary_metric", "audience", "analysis_date", "currency", "budget_minor", "stop_rule"],
    "distribution": ["channel", "intent", "destination", "currency", "budget_minor", "daily_cap_minor", "mode"],
    "route": ["release", "result", "installed", "fresh_install", "signed_out", "fallback"],
    "billing": ["release", "result", "currency", "sku", "price_minor", "restore_tested", "trial_eligibility_tested"],
    "retention": ["window", "eligible", "retained", "mature", "checked_at"],
    "evaluation": ["result", "decision", "guardrails", "analysis_date"],
    "learning": ["change", "heldout_test", "rollback", "result"],
    "cohort": ["cohort_id", "currency", "installs", "activated", "paid", "mature", "acquisition_cost_minor", "net_proceeds_minor", "delivery_cost_minor", "refunds_minor", "horizon"],
    "transaction": ["external_id", "currency", "type", "amount_minor", "occurred_at"],
    "review": ["external_id", "release", "locale", "rating", "theme", "severity", "confirmed"],
    "connection": ["provider", "account_id", "store_app_id"],
    "acquisition": ["analysis"],
}
LABELS = {"readiness":"Core journey test", "measurement":"Measurement contract", "claim":"Approved claim", "asset":"Authentic asset", "store":"Store destination", "experiment":"Experiment plan", "distribution":"Distribution packet", "route":"First-value route test", "billing":"Billing test", "retention":"Retention cohort", "evaluation":"Experiment evaluation", "learning":"Learning proposal", "cohort":"Economics cohort", "transaction":"Payment adjustment", "review":"Review finding", "connection":"Provider connection", "acquisition":"ASA / AEO worksheet"}
PROVIDERS = [
    {"id":"apple_ads","name":"Apple Ads","description":"Read campaign data for a verified organization. Keyword automation requires Advanced.","setup":"Upload an authorized P-256 key and enter the registered team, client and key IDs. Tokens renew locally; no server environment edits are required."},
    {"id":"app_store","name":"App Store Connect","description":"Read app identity, versions and paginated customer reviews. Complaints need investigation before confirmed findings.","setup":"Upload a team API .p8 key and enter its issuer, key and Store app IDs. Short-lived JWTs are signed locally; no server environment edits are required."},
    {"id":"aeo","name":"Answer engines","description":"Import captured query observations and citations; no invented visibility.","setup":"Use Evidence → ASA / AEO worksheet to import app-scoped observations. API and consumer UI results must stay separate."},
]

OPERATIONS = {
    1: {"tasks":["Identify the single consumer job and existing workaround.","Confirm the app, release, audience, activation event and tested locale.","Register the actual Store ID and owned destinations; keep unknown facts empty."],"deliverable":"Reviewed app manifest","verify":"A reviewer can reproduce the promised job on the named release."},
    2: {"tasks":["Test returning and new users through authentication, the core job, save and reload.","Test mobile controls, accessibility, errors and paywalls on the advertised build.","Review privacy manifests, required-reason APIs and unresolved critical failures."],"deliverable":"Build/device test receipts and defect decisions","verify":"Current receipts demonstrate the complete advertised journey with no unresolved P0."},
    3: {"tasks":["Map activation, paid conversion, retained value and consent before collecting events.","Document applicable AdServices or SKAN/AdAttributionKit attribution; preserve suppressed/null values as unknown.","Reconcile purchases, asynchronous refunds and actual remittances with stable event IDs."],"deliverable":"Measurement and reconciliation contract","verify":"A test event and late refund can be traced without double counting or exposing personal data."},
    4: {"tasks":["Import mature cohort counts with currency, horizon and source receipts.","Use actual net proceeds and delivery costs; verify commission enrollment rather than assume a rate.","Inspect paid CAC, contribution and missing denominators before proposing acquisition limits."],"deliverable":"Cohort contribution worksheet","verify":"The worksheet reconciles to supplied receipts; immature or unobservable outcomes remain inconclusive."},
    5: {"tasks":["Map each store claim to current proof and rights-cleared authentic screenshots.","Verify localized metadata, subscription disclosures and install/web fallback destinations.","Submit through the normal provider process, wait for its result, then inspect the public page before launch."],"deliverable":"Localized store handoff and public readback","verify":"Prepared, submitted, waiting-for-review and publicly available states are reported separately."},
    6: {"tasks":["Choose one proven app job and prepare the six problem/demo/limitation briefs.","Capture the exact build and document media rights and any trademark review.","Predeclare one primary outcome, guardrails, audience, stopping rule and analysis date."],"deliverable":"Creative briefs and bounded experiment plan","verify":"Every promised feature has current proof and every creative leads to the tested destination."},
    7: {"tasks":["Select an app-specific intent cluster and inspect actual demand evidence.","Use ASA Advanced data for the conservative CPT worksheet; keep Basic and other channels separate.","For AEO, publish only supported answers through an authorized handoff; record engine, locale, query and correct citations.","Have an independent reviewer inspect destination, limits and exact contents before manual provider execution."],"deliverable":"ASA/AEO distribution handoff","verify":"The public destination is live, limits are explicit, and provider results are read back; a packet is not a campaign."},
    8: {"tasks":["Test installed, fresh-install and signed-out entry paths for the exact promise.","Verify Universal Links and supported deferred routing on real devices; document Android and web fallback.","Confirm the first useful outcome and preserve unresolved routing failures."],"deliverable":"First-value route matrix","verify":"Each promised entry path reaches the same useful outcome without losing context."},
    9: {"tasks":["Verify localized SKU, price and trial eligibility in the actual checkout.","Test sandbox purchase, restore, cancellation disclosure and entitlement persistence.","Reconcile provider receipts and asynchronous refunds without simulating a successful purchase."],"deliverable":"Billing test and receipt matrix","verify":"Displayed terms, charged SKU and resulting access agree on the current build."},
    10: {"tasks":["Define retention around the app's useful-value cadence, not generic opens.","Import eligible and retained counts for the same mature cohort/window.","Inspect public review findings; investigate confirmed critical feature failures before acquisition continues."],"deliverable":"Retained-value cohort and review findings","verify":"The denominator is observable, the window is mature, and sampled widget impressions are not counted as value."},
    11: {"tasks":["Wait for the declared analysis window and inspect conversion, contribution and guardrails.","Reconcile late refunds, attribution gaps, review latency and campaign cost before comparison.","Report descriptive results separately from causal lift; select repair, collect, stop or another bounded test."],"deliverable":"Weekly experiment decision packet","verify":"The decision cites mature evidence and uncertainty; no download count is presented as business success."},
    12: {"tasks":["Propose one change from the evaluated bottleneck and retain its source version.","Define an untouched holdout and rollback before adopting the change.","Record the next observed result; do not silently modify prices, permissions or production campaigns."],"deliverable":"Versioned learning proposal","verify":"The proposed change is traceable and reversible, and adoption is distinct from a prepared hypothesis."},
}


def stages():
    """Return the twelve ordered stage definitions and dependency contracts."""
    return [dict(zip(("id","title","group","dependencies","description","inputs"), values),operations=OPERATIONS[values[0]]) for values in STAGES]
