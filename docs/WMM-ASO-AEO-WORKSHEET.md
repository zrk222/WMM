# WMM ASO/AEO worksheet (draft for owner review)

**Status: draft. This is Wize Marketing Machine, not a personal-finance app.**
Do not use money-manager, expense-tracker or budget keywords for WMM. Those
describe a different product and would misrepresent it.

The listing examples below are written for WMM's actual product: a local
app-marketing workspace where a founder sets a goal, approves scoped assistant
work and reviews evidence and receipts. They make no ranking, install, revenue
or growth claim.

Save a listing in **Results → Growth review → Save a listing**. The JSON below
is the `listing` object the form validates with `aso_validation.py`. You still
choose the current release, verify the claims and use the store's real counters.

## iOS — en-US (primary)

| Field | Value | Count |
| --- | --- | --- |
| Title | `WMM: App Marketing` | 18 / 30 |
| Subtitle | `Plan, approve, measure` | 22 / 30 |
| Keywords | `growth,campaign,creative,agent,approval,analytics,receipt,research,launch,aso,content,distribution` | 98 / 100 |
| Promotional text | empty until there is a dated, approved message | 0 / 170 |

```json
{
  "platform": "iOS",
  "locale": "en-US",
  "fields": {
    "title": "WMM: App Marketing",
    "subtitle": "Plan, approve, measure",
    "keywords": "growth,campaign,creative,agent,approval,analytics,receipt,research,launch,aso,content,distribution",
    "description": "WMM is a local workspace for app marketing. Add your app facts, audience, research sources and approved creative, then prepare evidence-bound briefs and campaigns. You choose the goal and approve each permission slip; your assistant works inside the limits you set. Review saved packets, receipts and connected analytics in one place. Publication and spending need separate exact approval. Default ad spending is zero. Missing source data stays unknown, and no growth result is claimed.",
    "promotional_text": ""
  },
  "surface": "MANUAL_METADATA",
  "test_fields": [],
  "rule_version": "2026-10-27.v2"
}
```

Notes:

- The keyword field repeats no word from the title or subtitle, uses singular
  forms, and has no spaces after commas.
- Do not add a secondary locale filled with English finance keywords. WMM's
  cross-indexing should use truthful translations of this positioning, after a
  native-language review.

## Google Play — en-US

| Field | Value | Count |
| --- | --- | --- |
| Title | `WMM: App Marketing` | 18 / 30 |
| Short description | `Plan, approve and measure app marketing with agent receipts.` | 60 / 80 |
| Full description | 636 / 4000 | see below |

```json
{
  "platform": "Android",
  "locale": "en-US",
  "fields": {
    "title": "WMM: App Marketing",
    "short_description": "Plan, approve and measure app marketing with agent receipts.",
    "description": "WMM is a local app-marketing workspace for founders and small teams.\n\nPlan the work: add your app, audience, release and the first useful user action. Bring research sources, approved claims and authentic screens.\n\nApprove the scope: choose the actions an assistant may take, with an expiry and a call limit. Every publish and spend needs a separate exact approval.\n\nFollow the evidence: review prepared packets, source hashes and connected analytics. Counts describe what a source recorded; missing data stays unknown.\n\nWMM does not promise rankings, installs or revenue. Use it to make one clear next marketing decision with receipts."
  },
  "surface": "MANUAL_METADATA",
  "test_fields": [],
  "rule_version": "2026-10-27.v2"
}
```

## Visual direction (owner to design and approve)

Replace raw UI screenshots with three outcome frames:

1. **Set the goal** — “One app. One next decision.”
2. **Approve the scope** — “You control every permission slip.”
3. **Open the receipts** — “See what ran and what the source recorded.”

Use the real Mission Control screens and synthetic data. Do not show invented
installs, revenue or rankings.

## AEO / entity notes

- Publish a factual `llms.txt` and Schema.org `SoftwareApplication`/`Organization`
  markup on WMM's own site. Describe the local workspace, approvals and evidence
  boundary; do not claim measured growth.
- Earned mentions must be genuine. No astroturfing, no invented reviews and no
  fabricated citations.
- Keep the desktop product story distinct from the separate native iPhone/iPad
  app. Verify the actual store presence and release before submitting metadata.

## Boundaries

- Owner review and the store's counters remain authoritative; `aso_validation.py`
  is a deterministic preflight, not a ranking prediction or provider approval.
- No paywall, PPP pricing, lifetime-free burst, rating-prompt or ad change follows
  from this worksheet. Those need separate product and spend approvals.
- A listing is not evidence of installs, retention or revenue.
