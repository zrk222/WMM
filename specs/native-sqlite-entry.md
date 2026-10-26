# Spec: native-sqlite-entry
Status: exact native connection boundary

## MUST - Functional core
### Requirements (EARS)
- When `HELPER_ENTRY` receives a non-native SQLite connection for a database helper, the system shall reject it with TypeError before executing helper statements. [R1]
- When `NATIVE_ENTRY` receives a native SQLite connection, the system shall return existing helper results without changing query text, ordering, transactions or approvals. [R2]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Reject fake connection
 Given HELPER_ENTRY receives a fake execute object
 When HELPER_ENTRY is invoked
 Then R1 rejects it before execute
Scenario: Preserve native behavior
 Given NATIVE_ENTRY receives a native SQLite connection
 When NATIVE_ENTRY is invoked
 Then R2 preserves existing results
```

Scope: existing db-parameter helpers in creative_briefs, creative_library,
discovery_store, funnel_store, managed_media_store, packaging_bindings and
packaging_store. No other workflows, UI or authority changes.
