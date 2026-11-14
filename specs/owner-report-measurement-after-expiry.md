# Keep measuring after publishing approval expires

When a campaign's approval ends, keep read-only measurement available without
renewing authority. An unresolved dispatch or blocked monitor keeps its recovery
guidance. Otherwise the report uses a matched delivery and its selected outcome
receipt to explain what can be interpreted. An empty eligible cohort has no
conversion rate, a shared tracking tag cannot identify a post, and a descriptive
rate is not proof of lift. Verified delivery without matched outcomes asks for
a measurement receipt. Previously retained report bodies are not rewritten.

`campaign_owner_reports.next_action` prioritizes unresolved post and paid
acknowledgments, pending dispatches and blocked monitors over historical
measurement. Even without a selected monitor, a saved pause observation that
showed effective delivery as ACTIVE directs the owner to verify the current
status of that exact campaign before interpreting results. The notice describes
what the retained observation showed, not the current provider state. An
acknowledgement is not provider confirmation.
`campaign_metric_definitions.historical_measurement` distinguishes incomplete
coverage, an unsupported metric, an unverified first-open definition and
inconsistent counts. None supplies a conversion rate. The outcome must match
the approved production app, campaign tag and window; a stored report is
returned unchanged on retry.

`tests/test_first_party_outcomes.py` covers each outstanding paid acknowledgment
with otherwise interpretable evidence, missing or unusable metrics, and exact
receipt selection. The advice is read-only and cannot renew permission or dispatch.
