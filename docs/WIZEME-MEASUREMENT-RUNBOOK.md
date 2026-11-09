# WizeMe measurement runbook (owner)

This is the operator procedure for producing the first honest measured result for
WizeMe. Development cannot run it for you: it needs your live accounts, a real
post and real source exports. Until those receipts exist, the result remains
**not established**.

Use it with the preregistration packet:
[WIZEME-PREREGISTRATION-20261108.md](WIZEME-PREREGISTRATION-20261108.md).

## What counts as a result

Pick **one** primary measure that a source can actually observe:

- **Installs** — an MMP install export keyed by the campaign token.
- **Retention** — a mature retention cohort from a connected or imported source.
- **Paid conversion** — reconciled purchase/subscription events for the cohort.

One chosen measure, a fixed window, a stated denominator and source receipts.
Anything else is commentary.

## Step 1 — Freeze the test

1. Recover the E12 baseline and set the two sample minima in the packet.
2. Choose the study window, landing path, creative ID and one source network.
3. Register the observational study through WMM. WMM issues the canonical link
   with `utm_campaign=<study_uuid>`.
4. Publish one approved post using that exact link. Save the provider post ID and
   permalink.

## Step 2 — Collect installs (MMP)

Export installs from your measurement partner for the same campaign token and
window. Ingest one exact batch through the owner-scoped install attribution
service (`mission_control.install_attribution.record_batch`). Batch shape:

```json
{
  "source": "APPSFLYER",
  "campaign_token": "<study uuid>",
  "request_id": "<new canonical uuid>",
  "source_receipt_sha256": "<64 lowercase hex>",
  "observed_at": "<UTC ISO time after the window>",
  "coverage": {"complete": true, "source_event_count": 0},
  "installs": [
    {"install_id": "<opaque token>", "state": "ATTRIBUTED", "occurred_at": "<UTC ISO time>"}
  ]
}
```

Rules:

- `install_id` is opaque. Never use emails, phone numbers or raw device IDs.
- `state` is `ATTRIBUTED`, `UNATTRIBUTED`, `SUPPRESSED` or `UNKNOWN`.
- Complete coverage states the source event count. Partial coverage keeps the
  count nullable and the report shows `PARTIAL`.
- Reusing a request identity with different content is rejected. Conflicting
  install identities reject the whole batch.
- The report returns counts per state and coverage. It never returns a rate, lift
  or causal claim. Zero is only zero with complete coverage.

A UI for this batch is not shipped yet; use the owner-scoped local service. Do not
paste tokens or customer data into a public issue.

## Step 3 — Collect retention or paid conversion (choose one)

- **Retention:** import a mature cohort for the same release, locale and window.
  Include eligible and retained counts, currency, horizon and source receipt.
- **Paid conversion:** import reconciled events/payments for the cohort. Late
  refunds restate the cohort; keep the source dates.

Missing platform split, installs, revenue or D1/D7/D30 stay **unknown**. Do not
substitute engagement counts.

## Step 4 — Read the result

1. Observational campaign report: tagged landings and linked registrations, with
   exclusions and coverage.
2. Install attribution report: attributed/unattributed/suppressed/unknown counts
   for the same campaign token, with coverage.
3. Retention or paid-conversion report: denominator, window, maturity and source
   hash.

Record the exact `as_of`, source hashes, sample sizes, exclusions and any unknown
values. If a source is incomplete, the result is inconclusive, not zero.

## Step 5 — Decide

Apply the packet’s decision rule:

- `TRACKING_VERIFIED_CONTINUE` — the tag and install link worked and the minima
  were met. This is not proof of growth.
- `TRACKING_BROKEN_REVISE` — the tag/install link failed; fix and register a new
  study.
- `COVERAGE_INCOMPLETE_COLLECT` — repair the collector and re-read the same
  window or register a new study.
- `INCONCLUSIVE_STOP` — minima not met or exclusions dominate.

Append the decision, UTC time, authority, actual result and next action to
[WIZEME-DOGFOODING.md](WIZEME-DOGFOODING.md). Keep failed and inconclusive
results in the record.

## Do not

- Do not invent an install, retention or conversion number.
- Do not call an engagement count a conversion.
- Do not call attribution “growth”.
- Do not extend the window or lower the minima after seeing data.
- Do not claim a causal effect without a holdout or a defensible comparison.

## Current status

No measured install/retention/conversion result exists for the WizeMe trial yet.
This runbook describes how to produce one; it is not evidence by itself.
