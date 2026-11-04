# Spec: github-preview-story
Status: owner-requested

## MUST - Functional core
### Description
Explain why founders and teams use Wize Marketing Machine: people set the goal
and approve a bounded scope, agents perform supported structured marketing work,
and owners inspect deliverables, source-backed analytics and receipts. Apply Nanna
storytelling and Prestige product design to the README and visual preview. Include
a usable synthetic sample UI, not just prose or screenshots.

### Requirements (EARS)
- The system shall return a plain-language founder and team story with a single primary next action and current capability boundaries through `inviting_story`.
- When a visitor opens the sample UI, the system shall let them select a goal, review exact sample consent, walk through research and creative stages and open a source-labelled report through `sample_workflow`.
- The system shall reject sample progression without consent, invalidate consent when inputs change, and label synthetic receipts, unknown outcomes and zero external effects through `sample_authority`.
- The system shall return accessible desktop and mobile previews with actual screenshots and working local links through `preview_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: inviting_story
  Given a founder deciding how to market an app
  When `inviting_story` opens the README or visual tour
  Then the goal, agent work, human consent and concrete deliverables are clear without claiming unimplemented teams or analytics coverage
Scenario: sample_workflow
  Given a visitor without accounts or credentials
  When `sample_workflow` is completed with a selected goal
  Then an inspectable sample plan, creative draft and report can be opened and exported
Scenario: sample_authority
  Given a draft sample agreement
  When `sample_authority` evaluates a missing approval or changed goal
  Then progression is unavailable until current consent and no provider operation occurs
Scenario: preview_proof
  Given actual desktop and mobile browser renders
  When `preview_proof` checks controls, focus, navigation and exports
  Then no overflow or script error occurs and screenshots show the actual labelled sample
```

## SHOULD - Technical
- Static preview only; no dependency, credential intake, runtime service or analytics collection.
- Reuse screenshots and existing operator/setup guides. Mark fixture metrics and observed operations separately.
- Verify Prestige audit, strict critique/challenge and rendered evidence, plus hash-bound CF workflow QA.

## Authorized parameters
