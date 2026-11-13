# Measurement data and repair contract

WMM must explain an unavailable number and the next repair. A missing receipt
is not zero spend, a missing purchase feed is not zero revenue, and a public
view count is not an attributed acquisition. The KPI register lists required
collector and evidence work; a documented repair does not complete that work.

## CAC and return on ad spend

The existing cohort event ledger now accepts an optional `economics` declaration:

```json
{
  "cost_basis": "MEDIA_SPEND",
  "revenue_basis": "NET_PROCEEDS",
  "attribution_status": "DECLARED_MATCHED",
  "spend_source": "campaign-report-reference",
  "currency": "CAD",
  "coverage_through": "2026-11-12T12:00:00+00:00"
}
```

All six fields are required when the declaration is present. Old cohort inputs
remain valid. They receive actionable economics gaps until the declaration and
matching evidence are supplied on a new immutable cohort. The declaration is
**supplied evidence, not a verified provider identity join**.

- CAC divides matching acquisition cost in minor currency units by distinct
  acquired subjects with an eligible positive first purchase through cohort
  maturity. Repeated purchases do not multiply the customer denominator.
- D7 and D30 ROAS divide revenue from each subject's first 7 or 30 days after
  install by matched media spend in the acquisition window. The purchase cutoff
  is exclusive. Every install must have a complete horizon before availability.
- Choose `NET_PROCEEDS` or `GROSS_REVENUE` according to what the imported purchase
  amounts actually represent. Net proceeds deduct linked refunds and add linked
  refund reversals through report time. Gross revenue uses the purchase amounts
  without presenting them as net proceeds. Fees must already be reflected in
  supplied net-proceeds purchase amounts; do not import refund-net amounts and
  subtract those refunds again.
- `TOTAL_ACQUISITION_COST` can support CAC but cannot substitute for media spend
  in ROAS. No currency conversion or cross-source identity matching is inferred.
- An explicit zero-cost receipt permits zero CAC when acquired payers exist.
  Zero spend cannot form a ROAS denominator. No payers cannot form a CAC
  denominator. Complete observed revenue coverage may legitimately show zero
  revenue with positive media spend.

Each metric returns its value or null, operands, currency, basis, sample counts,
window, source hash and `unavailable_data` repair actions. Revenue coverage must
extend through `as_of`, including late refund adjustments. Exact duplicate
provider/event identities count once; conflicting identities prevent a result.
`DECLARED_MATCHED` remains a declaration. UI and exports must not relabel it as
provider-verified attribution or causal evidence.

## Every data gap has a closure requirement

The machine-readable register at `specs/kpi-report-coverage.json` retains every
required metric, its current coverage, necessary inputs, repair action and
closure evidence. A metric remains incomplete until the corresponding source,
calculation, UI and export evidence exist. Collector permissions, rate limits,
privacy thresholds and an empty report are diagnosable states requiring the
appropriate next action; they cannot be converted to invented measurements.

## Unsuccessful experiments stay in the record

Use the existing append-only experiment assessments and action records. Keep
every blocked, inconclusive and evaluated assessment, including observed
declines and no observed difference. Preserve the hypothesis, source hashes,
analysis window, sample sizes, uncertainty, guardrail failures, owner decision
and remediation notes. A negative estimate is not automatically a statistically
established harm; a blocked evaluation is not a failed marketing hypothesis.
Local diagnostic tests are not a completed production experiment.

The owner should see what happened, why a decision is supported or unavailable,
and the next bounded test or data repair. New publication or spending still
requires current authority; a recommendation grants none.

When current report time is later than declared coverage, ROAS remains unavailable
for that current view. **Use covered economics snapshot** loads the selected
cohort at its completed coverage timestamp. Its visible Evidence as of date and
exported report identify that historical cutoff; other cohorts remain unchanged.
This read-only view neither advances coverage nor omits later ledger events.
