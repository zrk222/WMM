# Spec: creative-intelligence
Status: draft

## MUST - Functional core

### Requirements (EARS)
- The system shall return up to three distinct-creator references from an integrity-checked app-scoped research submission through `shortlist`.
- When sources are read successfully, the system shall prefer sources meeting the existing viral policy before eligible promising patterns through `evidence_tiers`.
- The system shall show the same shortlist to an agent and the owner, including the selection reason and a pattern-only next action through `shared_projection`.
- When a source is stale or the app revision has changed, the system shall reject new review actions outside the existing app and production authority through `no_new_authority`.

### Acceptance criteria (Gherkin)

```gherkin
Scenario: shortlist
 Given more eligible sources than the shortlist budget
 When the exact saved research is read
 Then up to three reference identities from distinct creators are listed deterministically
Scenario: evidence_tiers
 Given qualified and incomplete source observations
 When the shortlist is presented
 Then qualified sources are preferred and incomplete evidence stays labeled promising
Scenario: shared_projection
 Given an agent and an owner use the same retained submission
 When both inspect its sources
 Then both receive the same ranked source references and reasoning
Scenario: no_new_authority
 Given any shortlist including an eligible reference
 When the owner inspects that reference
 Then reuse, production, publication and spend remain separately governed
```

## SHOULD - Technical

- Derive the shortlist from the verified saved results and submission; preserve saved result bytes and hashes.
- Use the existing Hypit source review and approved original-brief workflows.
- Use WMM taxonomy and the exact creator-baseline policy. Treat paid, organic and unknown distribution types distinctly when the source supplies that evidence.
- Follow-up slices: short path from store link or app description; saved per-app searches and bounded refresh with documented data permissions; observation-linked creative element evaluation; one-variable tracked experiment and compare-to-manual proof.
- Keep platform availability, insufficient samples, publication and measured outcomes explicit. Use documented authorized sources only.

## Authorized parameters
SHORTLIST_LIMIT = 3
