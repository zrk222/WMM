# Spec: first-month-expectations
Status: approved

## MUST - Functional core
### Description
Explain the first day and a month of regular WMM use without promising marketing gains. Update WMM only; WizeMe is owned by another agent.

### Requirements (EARS)
- The system shall render the first-use and recurring-use text labels specified by EXPECTATION_LABELS in README, the public overview, desktop guidance and the native workspace through `expectation_pair`.
- The system shall render first-day text as choosing one app-growth question and preparing a desktop evidence packet or reviewing the native next preparation step with missing inputs through `first_day_scope`.
- The system shall render recurring-use text as a dated record of research, approved work, available results and continue, revise or stop decisions through `month_scope`.
- The system shall render explicit publication approval and unknown-measurement boundaries without promising growth or time savings through `claim_boundary`.
- The system shall render native expectation copy with semantic SwiftUI text styles and the NATIVE_READING_POINTS frame through `native_readability`.
- When the owner opens the desktop front door, the system shall display the expectation pair without issuing a provider request or creating authority through `no_effect`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: expectation_pair
 Given WMM's public, desktop and native introduction sources
 When `expectation_pair` checks the declared transition
 Then Day 1 and Around Day 30, with regular use are present
Scenario: first_day_scope
 Given the first day introduction
 When `first_day_scope` checks the declared transition
 Then it describes one question, a packet and missing inputs
Scenario: month_scope
 Given the recurring use introduction
 When `month_scope` checks the declared transition
 Then dated work and available results lead to a next decision
Scenario: claim_boundary
 Given expectation copy
 When `claim_boundary` checks the declared transition
 Then no guaranteed growth or measured time saving is claimed
Scenario: native_readability
 Given the native introduction
 When `native_readability` checks the declared transition
 Then semantic text sizes and 680 point reading width are retained
Scenario: no_effect
 Given the desktop overview
 When `no_effect` checks the declared transition
 Then opening the introduction creates no provider call or authority
```

## SHOULD - Technical
- Reuse existing sections, semantic system fonts, cards and approval workflows.
- Scope excludes WizeMe, new permissions, campaign engines and guaranteed outcomes.
- Render browser acceptance at 390 and 1440 pixels; native compilation remains an Apple CI check.

## Authorized parameters
EXPECTATION_LABELS = ["Day 1", "Around Day 30, with regular use"]
NATIVE_READING_POINTS = 680
