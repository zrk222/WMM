# Spec: brand-headers
Status: owner-authorized UI refinement

## MUST - Functional core
### Description
Make Wize Marketing Machine recognizable at the top of the workspace, public overview, interactive sample and native iOS workspace. Reuse the existing green upward-arrow mark and spell out the product name. Keep the app name, workspace switcher and workflow controls available.

### Requirements (EARS)
- When an owner opens the web workspace, the system shall return 1 visible product lockup through `workspace_header` above the workspace navigation, with the existing home link and readable full name.
- When a visitor opens the overview or interactive sample, the system shall return 1 matching mark and full name through `preview_header`, preserving the sample label, navigation and first action and showing the same header in the current synthetic sample screenshot.
- When the standalone iOS workspace renders, the system shall return 1 product lockup through `native_header`, preserving the selected app title and unlocking controls.
- When a header renders at narrow width or is read by assistive technology, the system shall return 1 readable product name through `accessible_brand`, with 0 horizontal page overflow and the decorative mark excluded from spoken text.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: workspace_header
 Given a local synthetic workspace
 When `workspace_header` renders
 Then the current mark and full name identify the app above its navigation
Scenario: preview_header
 Given the overview and sample
 When `preview_header` renders
 Then matching branding appears and the existing sample journey works
Scenario: native_header
 Given the native workspace
 When `native_header` renders
 Then the same identity appears with the existing app title and unlock controls
Scenario: accessible_brand
 Given narrow and desktop viewports
 When `accessible_brand` is inspected
 Then the product name is readable and no header overflows
```

## Scope
Brand and layout only. No grant, provider, networking, measurement or public claim changes. Use actual local rendered screenshots for verification. SwiftUI release evidence requires the native simulator checks.
