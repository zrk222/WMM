# Spec: creative-toolchain
Status: draft

## MUST - Functional core
### Description
Give marketers and scoped agents one WMM creative workflow with independently selectable Hypit, rea-video and Genjutsu steps.

### User roles
- The app owner selects tools, approves external processing and approves publication.
- A scoped agent may prepare, run authorized local analysis, and report results.

### Requirements (EARS)
- When the owner selects Hypit alone, the system shall return the existing organic workflow without optional analysis or external generation through `hypit_only`.
- When the operator requests rea-video analysis for admitted local footage, the system shall store timestamped observations bound and uncertain interpretations to the exact source and analyzer revision through `analysis_receipt`.
- When the owner approves a Genjutsu request, the system shall require current footage, audio and likeness rights, an approved provider and an exact maximum total charge before any upload through `external_admission`.
- When an external result returns, the system shall reconcile its durable request identifier and admit its decoded artifact only as a draft asset through `variant_receipt`.
- When analysis or a variant is handed to Hypit, the system shall verify app, source, manifest and artifact hashes before applying the existing brief, review, render and publication controls through `handoff_binding`.
- If an optional tool is disabled, unavailable or fails, the system shall show a specific recovery action and keep the Hypit path available through `independent_control`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: hypit_only
 Given a free organic campaign with an admitted reference
 When `hypit_only` runs with both optional tools disabled
 Then Hypit remains available and no external analysis or generation is requested

Scenario: analysis_receipt
 Given rights-cleared footage and a pinned local analyzer
 When `analysis_receipt` imports bounded shot observations
 Then observations remain linked to exact source bytes and interpretations remain labeled

Scenario: external_admission
 Given a metered generation request with no matching owner approval
 When `external_admission` checks the media upload
 Then it denies provider access without spending or transmitting media

Scenario: variant_receipt
 Given a saved submitted job with a provider request identifier
 When `variant_receipt` reconciles after restart
 Then it records one draft artifact or an actionable uncertain state without a second submission

Scenario: handoff_binding
 Given evidence from a different app or an older source version
 When `handoff_binding` prepares a Hypit brief
 Then the handoff is refused and no publication is scheduled

Scenario: independent_control
 Given an unavailable optional tool
 When `independent_control` opens the creative workflow
 Then the owner can use the ready tools and see the next step for the unavailable tool
```

## SHOULD - Technical
- Reuse managed media, discovery evidence cards, draft briefs, exact approvals, job receipts and experiment attribution.
- Default rea-video to an isolated local subprocess with network disabled and no inherited provider credentials.
- Prefer one explicit metered backend request over importing Genjutsu's standalone server and multi-provider pipeline.
- Route variant comparisons through the existing measurement workflow; keep view counts separate from app conversion.
