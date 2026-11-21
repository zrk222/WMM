# Campaign stale claims and checking effort

## Requirements (EARS)
- When a Page post has a verified receipt and permalink, WMM shall retain the exact approved wording, product-source hash, original source snapshot and receipt creation date. The receipt date is not proof of the exact provider publication time.
- When an organic publication reaches a provider-read PUBLISHED phase, WMM shall retain its approved caption and source snapshot. If the adapter has no public URL, WMM shall say so, rather than invent one.
- When an owner records an external listing or offer, WMM shall index its supplied URL, wording, claim IDs and publication date as owner-reported evidence, not provider-verified evidence.
- When a source manifest or claim fingerprint changes, the next private report shall flag the recorded artifact as STALE, retain its original wording, and request owner review without rewriting or deleting it.
- When a report is captured, WMM shall perform no fresh public or authenticated provider read. An explicit public-wording check shall reuse the bounded credential-free public reader outside SQLite writes. Missing wording is not proof the post was removed.
- When checking effort is recorded, WMM shall retain immutable source-bound counts, completed reviews and minutes. Repeated identities shall replay exact inputs only. Missing effort shall remain unknown, while recorded zero shall remain zero.
- When comparing compatible report snapshots, WMM shall show checking effort for the same declared half-open event window. It shall not infer total campaign cost, causal growth or billing from these observations.
- When an owner or reviewed scoped-agent request uses a foreign app, owner, scope or changed record hash, WMM shall reject it. Existing standing grants shall not silently gain these operations.

## Acceptance
`tests.test_marketing_review` exercises real protected owner HTTP, report storage, no-network reporting, source changes, immutable replay, foreign scope and effort windows. `tests.test_migrations` and the integrity drill exercise migration, backup and replay. `tests/campaign_owner_report_ui.test.cjs` covers escaped stale wording and unknown versus zero effort.

## Limits
Historical receipts without source snapshots cannot be backfilled as verified source lineage. Owners may index those artifacts explicitly. A source change is a review signal, not proof every public claim is false. Browser-rendered or authenticated public pages may remain unverifiable. Other listings and posts outside retained receipts need explicit indexing.
