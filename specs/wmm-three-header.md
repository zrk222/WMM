# Spec: wmm-three-header
Status: draft

## MUST - Functional core
### Requirements (EARS)
- The system shall display a Three.js illustration of three stages through `interactive_header`.
- When the visitor selects a stage, the system shall display its associated label and mark the selected control through `stage_selection`.
- If WebGL or JavaScript is unavailable, the system shall display the static poster through `preview_fallback`.
- When an Analytics result is displayed, the system shall display the evidence status label through `analytics_status`.
- When the saved experiment control rate exceeds 0 percent, the system shall display the signed relative change through `relative_change`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: interactive_header
 Given the overview is open in a WebGL capable browser
 When the artwork enters the viewport
 Then the local Three.js scene shows the three stages
Scenario: stage_selection
 Given the three stage controls
 When the visitor selects a stage with the keyboard
 Then its selected state and explanation update
Scenario: preview_fallback
 Given WebGL or JavaScript is unavailable
 When the visitor opens the overview
 Then the poster and demo link remain visible
Scenario: analytics_status
 Given a measured cohort and conflicting payment evidence
 When the Analytics overview renders
 Then labels and colors distinguish measured and conflicting evidence
Scenario: relative_change
 Given a saved experiment with a control rate of 20 percent and a treatment rate of 25 percent
 When the experiment result opens
 Then it shows a green 25 percent relative gain and a 5 percentage point difference
```

## SHOULD - Technical
- Keep the illustration decorative and use HTML controls, focus, labels and reduced motion.
- Render only while in use. Keep the pinned Three.js bundle and poster local.
- Preserve Analytics calculations, campaign approvals and provider behavior.
