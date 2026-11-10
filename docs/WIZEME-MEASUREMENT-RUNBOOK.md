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
window.

**Use the shipped UI first:** Results ? Install attribution ? **Import install
export**. Choose the original CSV/JSON file, source token, campaign token,
observed time, frozen window and the `install_id`/`state`/`occurred_at` columns.
WMM previews the coverage checklist and saves only a confirmation reference
until you confirm the exact export. The preview expires after 15 minutes.
Enter a status mapping when the source uses labels other than WMM's four states.
A complete export must be observed after the window ends and its count must
equal the imported and excluded rows. For a verified empty export, select
complete coverage and enter a source event count of zero. WMM remembers the
source and column mapping on this machine for the next import.

The command below checks and maps a file locally. To persist the export,
use the signed-in owner's import dialog.

```sh
python -m mission_control.install_import \
  --input installs.csv --input-format csv \
  --mapping mapping.json \
  --source APPSFLYER \
  --campaign-token <study uuid> \
  --observed-at <UTC ISO time after the window> \
  --window-start <UTC study start> --window-end <UTC study end> \
  --source-receipt-file installs.csv \
  --coverage-complete --source-event-count <export row count> \
  --out batch.json --checklist checklist.json
```

`mapping.json` names three columns and optional raw state values:

```json
{
  "install_id": "pseudonymous_install_id",
  "state": "attribution_status",
  "occurred_at": "install_time",
  "state_values": {
    "attributed": "ATTRIBUTED",
    "organic": "UNATTRIBUTED",
    "opt_out": "SUPPRESSED"
  }
}
```

The command exits nonzero if the checklist is `BLOCKED`. Read the checklist
before ingesting: it lists rows read/emitted, counts by state, missing values,
duplicate/conflicting install IDs, unmapped columns and incomplete coverage. Do
not edit a blocked batch into shape silently; fix the mapping or the source.

The mapper prints the normalized batch below. Review the checklist and use the
original export and matching mapping in the owner dialog.

```json
{
  "source": "APPSFLYER",
  "campaign_token": "<study uuid>",
  "request_id": "<new canonical uuid>",
  "source_receipt_sha256": "<64 lowercase hex>",
  "observed_at": "<UTC ISO time after the window>",
  "window": {"starts_at": "<UTC study start>", "ends_at": "<UTC study end>"},
  "coverage": {"complete": true, "source_event_count": 1, "excluded": {}},
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

The owner dialog verifies the original UTF-8 file bytes, including any BOM and
line endings, and records the source SHA-256. Use stable pseudonymous install
tokens prepared by your export process. Do not paste customer data into a
public issue.

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
2. In Results, choose **Open install report** beside the campaign token.
   Review attributed, unattributed, suppressed and unknown counts with the
   coverage, dates and source receipts. `MIXED` means some batches lack the same
   study link. Day 1, 3 and 7 views count retained installs through the selected
   cutoff. An export that ends early or was observed before the cutoff shows
   partial coverage. An unobserved count remains unknown.
3. Retention or paid-conversion report: denominator, window, maturity and source
   hash.

The Results page shows `No install export yet` until a batch exists. That is an
honest waiting state, not zero installs.

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
