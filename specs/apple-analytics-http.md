# Spec: apple-analytics-http
Status: draft

## MUST - Functional core
### Description
Expose a fresh owner-only local view, inventory queue and schedule control for the selected app and its existing Apple analytics source.

### Requirements (EARS)
- When an owner requests the view, the system shall return only current app-bound report metadata through `scoped_view`.
- When an owner queues inventory, the system shall use the existing read-only sync job through `inventory_queue`.
- When an owner enables or pauses refresh, the system shall store the change with the existing schedule implementation through `schedule_control`.
- If the app, connection, report, role or session changes, the system shall reject stale authority through `transaction_guard`.
- The system shall reject malformed requests and nonlocal or queried addresses through `request_validation`.
- The system shall retain unknown metrics and redact credentials, URLs and provider errors through `privacy`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: scoped_view
  Given a current app and source with saved inventory
  When `scoped_view` is requested by the verified owner
  Then only selected source report metadata is returned
Scenario: inventory_queue
  Given a current app and Apple connection
  When `inventory_queue` is requested by the verified owner
  Then one existing sync job is queued with bounded options
Scenario: schedule_control
  Given a current source inventory containing a downloads report
  When `schedule_control` is requested by the verified owner
  Then the existing scheduler saves or pauses the selection
Scenario: transaction_guard
  Given an app source or owner role changes before a write
  When `transaction_guard` checks the write
  Then the write is rejected before commit
Scenario: request_validation
  Given an invalid address or input body
  When `request_validation` handles the request
  Then the request is rejected
Scenario: privacy
  Given provider metadata contains private fields
  When `privacy` constructs the response
  Then only the allowlisted public fields are returned
```

## SHOULD - Technical
- Use fresh identity, bound_owner and protected transactions. No token grants owner access.
- No provider call, credential access, spending, or external publishing occurs in these request handlers.
- Inventory report instance count describes metadata only and is not a metric.
- The owner view and saved report distinguish an absent Apple report stream, an incomplete inventory, and an active stream waiting for files. They identify the next action from the saved state, prioritize repair of an unavailable key, and never create a provider report stream or interpret missing files as zero downloads.

## Authorized parameters
MAX_INVENTORY_JOBS = 1000

## App Store campaign download acceptance

In **Connections → Apple analytics**, refresh the inventory, open **Measure App Store
campaign downloads**, and paste the campaign link generated in App Store Connect.
Choose an available daily Detailed file to collect. After the job completes, reuse
the link and select a two-letter storefront and up to 31 calendar days. Processing
date selects the file; the dates in the results are the dates of the downloads.

- Accept Apple tracking parameters only on an official HTTPS product link for the
  selected app. Publishing preflight must preserve both the product and query.
- Collect only a complete Detailed report's selected daily instance through the
  existing app/source-bound worker. Store the campaign name as a hash, and discard
  the optional referrer and other Detailed dimensions.
- Count only Apple-reported first-time downloads matching the campaign, storefront
  and day. A reported zero stays zero. An absent row stays unknown, including
  when Apple suppresses small counts. Standard report rows, website visits,
  first opens and paid subscriptions are separate measurements.
- Each numeric row links to the fingerprint of its retained source. The view
  provides counts, not an estimate of incremental lift.
