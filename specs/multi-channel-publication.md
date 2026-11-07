# Spec: multi-channel-publication
Status: approved owner request, November 6, 2026

## MUST — Functional core
### Description
Organic publication and observation on Instagram, TikTok, YouTube Shorts and LinkedIn, alongside existing Facebook workflows, for owners and their scoped agents.

### User roles
- Owner: connects accounts and grants exact publication authority.
- Agent: prepares, executes and reports inside current owner authority.

### Requirements (EARS)
- When CHANNEL_SETUP selects facebook, instagram, tiktok, youtube or linkedin, the system shall derive read or publish scopes from that registered provider contract and reject ads access for every provider except facebook. through `mc1`.
- When CHANNEL_CONNECT completes consent, the system shall store the verified provider subject, selected destination, actual granted scopes and protected credentials apart from publication authority. through `mc2`.
- When PUBLICATION_PREVIEW prepares an organic action, the system shall bind the app revision, provider, connection revision, destination, content, media SHA256, rights, privacy and disclosures into one immutable review hash before owner approval. through `mc3`.
- When PUBLICATION_EXECUTE runs an approved action, the system shall check current authority before each provider call, reserve one durable request identity and retain provider identifiers before advancing its stage. through `mc4`.
- If PUBLICATION_RECOVERY cannot establish whether a mutation succeeded, the system shall retain UNKNOWN and require reconciliation before another mutation; safe status reads shall retain the same intent identity. through `mc5`.
- When an approved organic publication item becomes due, the system shall store one job bound to its due time and channel in the existing worker queue and reject duplicate dispatch after restart or OFF. through `mc6`.
- When CHANNEL_REPORT reads a retained intent, the system shall distinguish acceptance, processing, publication and public visibility, attach dated source receipts, and preserve unavailable metrics as null with an explanation. through `mc7`.
- When CHANNEL_UI or CHANNEL_AGENT selects an action, the system shall return the same versioned preview, approval, execution, status and recovery contracts without creating authority from account connection or model output. through `mc8`.
- While FREE_CAMPAIGN executes on any channel, the system shall store 0 units of ad spending and preserve all existing Facebook execution, rights, revocation and exact destination checks. through `mc9`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: mc1
 Given owner selects a provider and capability
 When `mc1` checks the declared transition
 Then provider permissions match the selected capability
Scenario: mc2
 Given provider confirms one destination
 When `mc2` checks the declared transition
 Then credentials remain protected apart from publication authority
Scenario: mc3
 Given one exact organic action is prepared
 When `mc3` checks the declared transition
 Then changed content or destination invalidates the review
Scenario: mc4
 Given current owner authority exists
 When `mc4` checks the declared transition
 Then a durable intent precedes external effects
Scenario: mc5
 Given a provider write response is lost
 When `mc5` checks the declared transition
 Then the same intent is reconciled before another mutation
Scenario: mc6
 Given an approved due item survives restart
 When `mc6` checks the declared transition
 Then one due item produces no duplicate publication
Scenario: mc7
 Given a provider metric is unavailable
 When `mc7` checks the declared transition
 Then the report keeps a dated null and reason
Scenario: mc8
 Given owner and agent select the same action
 When `mc8` checks the declared transition
 Then both use the same versioned service contract
Scenario: mc9
 Given an organic action is authorized
 When `mc9` checks the declared transition
 Then ad spending remains zero
```

## SHOULD — Technical/structural
- Reuse social setup, OS-protected secrets, app isolation, current authority checks, durable jobs, schedule lifecycle and receipt projections.
- Provider adapters implement documented authentication, transfer, processing and observation protocols. One channel credentials or approval never authorize another.
- Protect upload-session URLs in the credential store, outside reports and agent context.
- Validate provider media rules and return concrete corrective actions before dispatch.
- Keep synthetic tests, actual account acceptance, public visibility and measured marketing impact as separate evidence classes.

## SHOULD NOT — Implementation details
- Add no paid spending or automatic approval from model output.

## Decision logic (factory candidates)
| # | if | then |
|---|----|------|
