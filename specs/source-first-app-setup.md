# Spec: source-first-app-setup
Status: draft

## MUST - Functional core
### Requirements (EARS)
- The system shall store a local named app draft from a supported public HTTPS link before requesting optional details through `draft_from_source`.
- When a draft is saved, the system shall show the current app source review through `review_entry` without reading the public source.
- When the inspected source is an official Apple listing, the system shall return its exact app ID as a proposed field through `official_listing_identity`.
- If a source is invalid or the selected app changes, the system shall reject the link or stale screen transition through `recover_without_overwrite`.
- The system shall display the existing manual no-link form and reject unapproved field changes through `manual_fallback`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: draft_from_source
 Given a first-time operator with an app name and public link
 When the draft is saved
 Then a local app exists with unresolved facts still blank
Scenario: review_entry
 Given a deliberately saved app draft
 When the screen opens the source review
 Then no public request is sent until the operator chooses to read
Scenario: official_listing_identity
 Given an inspected official Apple page with a known listing ID
 When metadata is proposed
 Then the ID provenance points to the official listing
Scenario: recover_without_overwrite
 Given an invalid link or changed app during save
 When a source-first draft is submitted
 Then the operator retains input or stays with the new selection
Scenario: manual_fallback
 Given an operator without a public link
 When the full manual setup is saved
 Then the existing goal entry opens
```

## SHOULD - Technical
- Use the existing named app save route, URL guard, source proposal, and exact field application.
- Keep website metadata unverified. Release, locale and activation remain user-reviewed.
- Do not execute page instructions, follow store links in the page or bypass robots checks.
- Initial link support covers public HTTPS websites and Apple listing URLs. Google Play package setup continues through the existing Play path.
