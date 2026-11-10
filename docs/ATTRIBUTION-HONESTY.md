# Attribution honesty

Status: **policy and story guide**, not a measured result.

WMM’s attribution story is what it refuses to claim as much as what it reports.

## What WMM reports

- **Tagged-study visits and linked registrations** from saved source observations, with coverage and exclusions.
- **Install counts by state** (`ATTRIBUTED`, `UNATTRIBUTED`, `SUPPRESSED`, `UNKNOWN`) for one campaign token and frozen window.
- **Coverage state:** complete only when the source event count supports it; otherwise partial.
- **Cumulative install views** for day 1, 3 and 7, counted as distinct installs up to that day. These are **not** D1/D3/D7 retention.
- **Retention only from a mature retention cohort** with eligible/retained counts, window, currency and source receipt.
- **Payment/retention results only** when the imported or connected source supports the denominator.

## What WMM refuses

- Invented or estimated D7/D30 retention from install views.
- Engagement counts presented as installs, conversions or growth.
- Causal lift from a before/after comparison without a predeclared control or credible comparison.
- “Zero” when coverage is incomplete. Missing stays unknown.
- A single blended “ROI” or LTV number without source joins and a stated denominator.
- Results from synthetic fixtures, demos or benchmarks presented as customer outcomes.

## The story to tell

> We keep the source dates, definitions, denominators, coverage and receipts. If the data cannot support D7 retention or causal lift, WMM says so instead of producing a number.

## Sales use

Use this language only with a real study, a frozen window, a source export and a documented decision. Before that, say: **“The measurement path is prepared; no result exists yet.”**

See [WIZEME-MEASUREMENT-RUNBOOK.md](WIZEME-MEASUREMENT-RUNBOOK.md) and the analytics coverage matrix in [WMM-KPI-COVERAGE.md](WMM-KPI-COVERAGE.md).
