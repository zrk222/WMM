# Spec: content-packaging-t4
Status: guided owner authoring and neutral preproduction preview

## MUST - Functional core
### Requirements (EARS)
- When `VARIANT_EDITOR` opens for a current app owner, the system shall return editable audience, outcome, title, thumbnail layout, opening frame, hook, CTA and exact current source/brief/product proof selections, and save immutable revisions through packaging.save. [R1]
- When `SHOT_EDITOR` opens for a saved variant, the system shall return editable ordered script segments and A-roll, B-roll, screen recording, graphics and audio shots with source timestamps, asset/media selections, claim text and exact proof links; segment hashes shall match the server canonical SHA256 contract. [R2]
- When `FEED_PREVIEW` is requested for a saved current variant, the system shall render its title and selected uploaded thumbnail alongside 2 through 3 selected saved sources at desktop 1440 pixels or mobile 390 pixels, using equal card styling, optional hidden identities, deterministic seeded ordering and actual two-line title truncation. [R3]
- When `PREVIEW_EVIDENCE` is reported, the system shall return source/revision identities and owner-entered simulation observations of at most 2000 characters separately from unavailable measured CTR, installs and app sales. [R4]
- When `UNCONFIRMED_SAVE` occurs, the system shall preserve the exact input in memory, block another write for that scope, offer reconciliation and allow at most 1 explicitly requested identical retry after NO_REVISION_OBSERVED, with no automatic resubmission. [R5]
- When `SCOPE_CHANGE` alters app, setup revision or principal or a dialog closes, the system shall invalidate active requests and clear private dialog contents without applying a late response to another context. [R6]
- When `REPORT_REQUEST` is made, the system shall return the selected saved plan or preview as PDF print view, JSON and CSV, with operational counts and explicit source/evidence status. [R7]
- When `USER_NAVIGATION` uses keyboard or a viewport at 390 pixels, the system shall return labelled controls, 44-pixel action targets, visible focus, announced loading/error/success states and back/cancel recovery without discarding fields after a rejected save. [R8]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Original candidate
 Given VARIANT_EDITOR has current owner and app evidence
 When VARIANT_EDITOR saves a title and thumbnail selection
 Then R1 returns a new immutable revision
Scenario: Script and footage
 Given SHOT_EDITOR has selected script and original media
 When SHOT_EDITOR reorders and saves shots
 Then R2 preserves order and source timestamps with canonical hashes
Scenario: Contextual comparison
 Given FEED_PREVIEW has two selected reference sources
 When FEED_PREVIEW renders both device sizes with the same seed
 Then R3 preserves card order and equivalent styling
Scenario: Preview observations
 Given PREVIEW_EVIDENCE has an owner readability note
 When REPORT_REQUEST exports it
 Then R4 and R7 label it as simulation evidence with unknown measured outcomes
Scenario: Uncertain response
 Given UNCONFIRMED_SAVE did not return a confirmed receipt
 When UNCONFIRMED_SAVE is reconciled
 Then R5 offers no automatic replay
Scenario: Context changes
 Given SCOPE_CHANGE invalidates a pending read
 When SCOPE_CHANGE finishes
 Then R6 rejects its late response
Scenario: Accessible editing
 Given USER_NAVIGATION uses keyboard on a mobile viewport
 When USER_NAVIGATION corrects an invalid form
 Then R8 retains fields and provides named recovery controls
```

The first ASSET in variant app_proofs supplies the local thumbnail preview;
thumbnail text describes its layout. Uploaded local images only; never fetch
remote thumbnails from source URLs. Existing upload/Drive/editor controls remain
separate and accessible. A saved draft, preview or PDF grants no render, reuse,
publication, spending or app-sales authority. Live YouTube reads and production
handoff remain T2 and T5. This packet adds no top-level navigation item.
