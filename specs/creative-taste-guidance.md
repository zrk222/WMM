# Spec: creative-taste-guidance
Status: draft

## MUST - Source-bound video taste guidance
### Requirements (EARS)
- The system shall return machine-readable video purpose, brand, hook, pacing, captions, framing, transitions, audio and CTA guidance through `video_taste`.
- The system shall bind guidance provenance and selected public preference references to an approved source hash through `taste_provenance`.
- The system shall deliver the hashed source to actual reviewed draft proposal prompts and reject changed context before inference through `taste_delivery`.
- The system shall return separate deterministic media checks and evidence-based aesthetic review with at most 2 proposed revision passes through `taste_review`.
- The system shall retain human approval and standing-scope boundaries and return REQUIRED_NOT_COMPLETE for executing-agent integration through `taste_authority`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: video_taste
  Given a selected app public manifest
  When `video_taste` prepares guidance
  Then five adapted laws and purpose lenses cover actual video decisions
Scenario: taste_provenance
  Given approved brand and purpose preferences
  When `taste_provenance` emits a source
  Then the source cites app_manifest and contains policy and upstream hashes without workstation paths
Scenario: taste_delivery
  Given a tested model route and exact reviewed proposal
  When `taste_delivery` constructs the actual provider prompt
  Then creative_taste is an approved citation and changed guidance rejects stale approval
Scenario: taste_review
  Given an uninspected render
  When `taste_review` describes required checks
  Then missing measurements and aesthetic review stay required rather than passed
Scenario: taste_authority
  Given a future autonomous video workflow
  When `taste_authority` describes capabilities
  Then advisory guidance grants no tools, approval, spend or completed execution profile
```

## Required execution integration - REQUIRED_NOT_COMPLETE
An executing video agent must consume this same guidance under its selected app,
preferences and admitted scope, inspect actual rendered frames/audio/captions,
record hash-bound observations, enforce the lower approved revision/call/spend
budget, revise through implemented project operations and export the inspected
result. This advisory-source slice does not implement that executor, imported
media ingestion, UGC stitching or unsupported autonomous render profiles.
HTML Prestige audits do not certify a video. Current approved model tasks remain
tool-free draft generation; no operation catalog or execution permission expands.

## Authorized parameters
The guidance proposes no more than 2 revision passes; current authority may allow
fewer or none. Existing context and UTF-8 prompt bounds stay unchanged.
MAX_PROPOSED_REVISIONS = 2
