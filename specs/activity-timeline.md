# Spec: activity-timeline

Status: draft

## MUST - Functional core
### Description
Project existing app-owned local records into one read-only, chronological
timeline. The projection adds no table, no provider read and no authority. Its
purpose is to let one operator reconstruct prepared, approved, executed and
observed work without opening each domain surface.

### Requirements (EARS)
- The system shall project, for one app, the closed kinds `AUDIT`, `JOB`,
  `APPROVAL`, `VERIFIED_REVIEW`, `PROVIDER_ACTION`, `AGENT_GRANT` and
  `SOURCE_READ` from their existing tables through `activity_timeline`.
- The system shall order events newest first by stored creation time and event
  identity, without rewriting any stored timestamp.
- The system shall include for each event only a closed schema: identity, kind,
  action, nullable status, creation time, a receipt reference with the source
  table identity and a lowercase SHA-256 when the source stores one, and an
  explicit `caused_by` list.
- The system shall set `caused_by` only when one stored audit detail identity
  matches exactly one other projected event, and shall leave the list empty when
  the reference is absent or ambiguous.
- The system shall filter by one kind and one uppercase status token and shall
  page with an opaque cursor over a stable `(time, kind, identity)` key.
- The system shall return explicit coverage: per-kind stored counts, any source
  bounded at its read limit, whether another page exists, and the boundary that
  provider effects and unrecorded links are not inferred.
- The system shall never return stored payloads, job results, review packets,
  grant token hashes or audit detail beyond the fields above.
- The system shall expose the first page in the owner workspace as
  `activity_timeline` and one filtered, paged owner read at
  `/api/apps/{app}/activity/history` accepting only `kind`, `status`, `cursor`
  and `limit`.
- The system shall expose the same read as `activity.history` in the fixed
  operation catalog for CLI and MCP, marked read-only, carrying only those four
  optional fields and requiring a current scoped grant or owner session.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: activity_chronology
  Given audit, job, approval, review, provider-action, grant and source-read rows for one app
  When `activity_timeline` reads the app
  Then one event per stored row is returned newest first
  And no other app's rows appear

Scenario: activity_causal_link
  Given an audit row whose detail identity matches exactly one job row
  When the timeline is read
  Then that audit event names the job event in caused_by
  And an audit row with no match or an ambiguous match names nothing

Scenario: activity_filters
  Given a mixed synthetic history
  When the read filters by kind and status
  Then only matching events are returned
  And unknown kinds, malformed status tokens and malformed cursors fail

Scenario: activity_pagination
  Given more events than one page
  When the read pages with its cursor
  Then each event appears once in the same stable order
  And the final page reports complete true

Scenario: activity_privacy
  Given an audit detail or source row containing extra content
  When the timeline is read
  Then the event contains only the closed schema
  And no payload, result, packet or token hash is disclosed
```
