# Spec: goal-connection-wizard
Status: draft

## MUST - Functional core
### Description
Present outcome-specific owner connection selection and the existing authoritative read-only readiness report. No policy or grant is created.

### Requirements (EARS)
- The system shall display exact fixed goal workflows and current app-owned connection choices through `select_connections`.
- When the owner requests readiness, the system shall send only the exact selection to the existing owner readiness route through `inspect_readiness`.
- If app, manifest, principal, dialog or selected goal changes, the system shall reject late readback through `stale_readback`.
- If the owner edits the selected agent, accounts or workflows during a readiness check, the system shall keep the edited form and request a new check through `selection_changed`.
- The system shall display every selected workflow blocker and a fixed repair action through `show_blockers`.
- The system shall display readiness as preparation for scope review and shall issue no execution authority through `no_authority`.
- The system shall display owner-reviewed organic Instagram, TikTok, YouTube and LinkedIn work alongside Facebook through `organic_channels`, naming the supported connection path without treating adapter availability or a read-tested account as publication permission.
- Where the current app has an App Store listing, the system shall offer Apple download tracking in the campaign and measurement goals. For the campaign goal, the system shall offer social account setup when a read-tested Facebook Page is missing, or exact campaign review when the Page has a saved read test. Both entry points shall reject stale app actions and issue no approval.
- When the current app owner opens campaign readiness, the system shall offer the app's social account setup without requiring an agent. The link shall share the app, goal, owner and dialog freshness checks of the agent setup options.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: select_connections
 Given an existing selected app and goal
 When `select_connections` checks the selected state
 Then only fixed workflow choices and current app-owned profiles appear
Scenario: inspect_readiness
 Given a current authenticated owner selection
 When `inspect_readiness` checks the selected state
 Then only the exact selection is submitted without purpose or limits
Scenario: stale_readback
 Given a replaced dialog or changed app identity
 When `stale_readback` checks the selected state
 Then late readback does not replace the current interface
Scenario: selection_changed
 Given a readiness request is pending for the original account or workflow selection
 When the owner edits the selection before the response arrives
 Then the response does not replace the edited form and the owner can check again
Scenario: show_blockers
 Given a readiness inventory with blocked selected workflows
 When `show_blockers` checks the selected state
 Then all blockers and fixed repair actions appear
Scenario: no_authority
 Given a readiness check
 When `no_authority` checks the selected state
 Then no grant or policy or campaign is activated
Scenario: organic_channels
 Given a campaign goal and current app-owned connections
 When organic publication is selected
 Then the wizard names Instagram, TikTok, YouTube Shorts and LinkedIn
 And direct Instagram Login is directed to the supported Facebook Page connection path
 And the exact owner publication approval remains required
Scenario: campaign_account_setup
 Given the owner selected the campaign goal
 When the owner selects Check Facebook and Meta accounts
 Then focus moves to the selected app's social account setup
 And no readiness request or authority change is made
```

## SHOULD - Technical
- Existing Readiness.report remains authoritative; frontend badges never establish freshness.
- Campaign scope remains separate, paid effects require exact owner approval.
- Read-only selection keeps provider credentials outside the form; no raw token inputs.
