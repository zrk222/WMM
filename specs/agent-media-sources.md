# Spec: agent-media-sources
Status: implementation

## MUST - Functional core
### Requirements (EARS)
- The system shall return at most 1000 app-owned uploaded source descriptors with kind, identity, hash, decoded metadata and current reuse state through `media_sources`.
- The system shall reject ungranted or foreign app source discovery through `media_grant` using the existing operation authority without granting review or binary access.
- The system shall return source discovery without raw video, local paths, owner evidence or review history through `media_redaction`.
- The system shall return the same current source projection in owner HTTP, CLI and official MCP through `media_parity`, including revoked and stale status without implying reuse permission.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: media_sources
  Given uploaded clips in two apps
  When `media_sources` lists the selected app
  Then only its bounded source descriptors are returned
Scenario: media_grant
  Given a grant lacking source discovery or for another app
  When `media_grant` admits the request
  Then discovery is rejected before private source reads
Scenario: media_redaction
  Given an owner attestation containing private evidence
  When `media_redaction` projects uploaded source descriptors
  Then evidence, history, paths and bytes are excluded
Scenario: media_parity
  Given an owner-approved and later revoked source
  When `media_parity` reads through owner HTTP, CLI and official MCP
  Then each response exposes the same current scoped descriptors and revocation
```

## WON'T - Out of scope
No binary upload/download, attestation, publication or provider authority is added. The agent uses approved existing source references through editor operations. Currentness is inspected during discovery; actual source bytes and reuse are reverified by editor save and render.
