# Spec: campaign-goal-tracking
Status: draft

## MUST - Functional core
### Requirements (EARS)
- When the campaign goal is selected, the system shall display the existing organic study action through `campaign_entry`.
- When the selected campaign evidence packet opens, the system shall display its saved evidence requirements and the organic study action through `packet_entry`.
- When the organic study action is chosen, the system shall open the current app study history without creating a study or granting authority through `read_before_save`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: campaign_entry
 Given the operator selected the campaign goal for the active app
 When the goal card is rendered
 Then Plan a tracked organic post is visible alongside the separate campaign setup
Scenario: packet_entry
 Given an open campaign evidence packet
 When the operator reads its preparation requirements
 Then the existing requirements remain visible above the saved packet controls
Scenario: read_before_save
 Given an authenticated owner and an app-scoped campaign packet
 When the owner opens the organic study from the packet
 Then the existing study history opens and a separate explicit save is still required
```

## SHOULD - Technical
- Reuse the current observational campaign route, owner scope and report.
- Keep first-party tracking setup separate from social connection, exact publish approval and live reporting.
- Keep the other goal cards and all twelve pipeline stages.
