# Recurring private rule reports

An owner can tell a saved Results rule to keep private reports when the evidence changes. The owner chooses one exact report template and a save limit between one and the scheduled review limit. Old schedules and schedules with no explicit save limit still save at most once.

- A due review must meet the existing active schedule, owner, app revision, saved rule, study, current source and template checks. Existing dismissal, cooldown, and incomplete-evidence behavior still applies.
- For an approved limit above one, retain a maximum of one report per distinct evidence revision. Compare the retained observations, KPI definitions, campaign and monitor receipts, and saved assessment or outcome evidence. A different evaluation clock, an unchanged record edit, a previous report comparison, or unrelated rule facts do not create a new revision.
- Keep the approved template's exact app, source selection and measurement window. Save the report and its run receipt in one transaction. Retry and restart must preserve the limit and deduplication.
- Results shows the approved limit, saves used, the latest private receipt and the existing stop control. The rule may keep evaluating when the report limit is met, but no further captures are allowed.
- The integration does not read providers, send messages, publish, spend, or issue authority.
