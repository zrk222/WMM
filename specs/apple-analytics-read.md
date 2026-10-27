# Spec: apple-analytics-read
Status: implementation in progress; bulk metric ingestion and scheduled UI acceptance remain required.

## MUST - Existing read transport
### Requirements (EARS)
- When `APPLE_ANALYTICS` reads a selected app connection, the system shall validate the returned app identity and traverse only that app's typed analytics requests, reports and instances using its existing protected credential. [AA1]
- When `APPLE_ANALYTICS` receives a malformed resource, foreign relationship, conflicting duplicate or unsafe pagination URL, the system shall reject that response before issuing another authenticated request. [AA2]
- When `APPLE_ANALYTICS` reaches a page or report budget, the system shall return partial coverage and uninspected resources explicitly rather than imply a complete measurement. [AA3]
- When `APPLE_ANALYTICS` has no generated report instances, the system shall return a waiting state with null metric observations rather than zero downloads, sales or retention. [AA4]
- When `APPLE_ANALYTICS` uses the existing sync worker, the system shall retain app scope, observation time and source hashes without creating reports, granting access or changing provider data. [AA5]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Scoped analytics inventory
 Given APPLE_ANALYTICS has a protected app connection
 When APPLE_ANALYTICS reads its report inventory
 Then APPLE_ANALYTICS returns typed reports and dated instances for that app
Scenario: Hostile provider response
 Given APPLE_ANALYTICS receives an unsafe pagination destination or foreign app relationship
 When APPLE_ANALYTICS validates that response
 Then APPLE_ANALYTICS rejects it before a follow-up request
Scenario: Bounded observation
 Given APPLE_ANALYTICS has more reports than its read budget
 When APPLE_ANALYTICS stops reading
 Then APPLE_ANALYTICS returns partial coverage and uninspected reports
Scenario: Reports are not ready
 Given APPLE_ANALYTICS has an ongoing request with no instances
 When APPLE_ANALYTICS reads the current inventory
 Then APPLE_ANALYTICS returns waiting and null metric observations
Scenario: Existing worker boundary
 Given APPLE_ANALYTICS runs through an app-bound sync job
 When APPLE_ANALYTICS saves the result
 Then APPLE_ANALYTICS returns source hashes without provider mutations
```

This packet establishes read readiness and report-instance discovery. It does not
complete MV1: bounded segment downloads, schema-aware metric ingestion, refresh
scheduling, UI/CLI/MCP acceptance and actual populated report verification remain
required. No private account IDs or credentials belong in committed fixtures.
