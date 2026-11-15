# Spec: observational-collector-handoff
Status: draft

## MUST - Functional core
### Requirements (EARS)
- When a study has a declared collector, the system shall return its exact setup with the authorized tagged URL through `setup_projection`.
- When a study has no declared collector, the system shall return null in the collector setup field through `legacy_study`.
- When the owner downloads collector setup, the system shall emit the same declared setup without publishing or marking it verified through `download_setup`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: setup_projection
 Given a current study and a named collector
 When the authorized link operation reads the study
 Then the response binds the collector event names to that study, app, tagged URL and fixed window
Scenario: legacy_study
 Given an existing study with no collector declaration
 When the authorized link operation reads the study
 Then the original tagged link is returned with null collector setup
Scenario: download_setup
 Given the owner views a study with a declared collector
 When the owner selects Download collector setup
 Then the file matches the returned setup and labels the source as declared and unverified
```

## SHOULD - Technical
- The existing link operation retains the current app, study hash and owner or scoped-agent checks.
- The setup contains no event data, identifiers for people, credentials or approval.
- A final receipt for both event types after close remains required.
