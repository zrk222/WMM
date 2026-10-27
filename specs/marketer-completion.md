# Spec: marketer-completion
Status: required owner additions; actual acceptance pending

## MUST - Functional core
### Requirements (EARS)
- When `LIVE_READ` collects permitted WizeMe observations, the system shall retain app/source identity, timestamps, denominator, scheduled refresh, failure/recovery and fallback-import evidence without replacing unknown coverage with zero. [MV1]
- When `GOVERNED_EXECUTION` receives exact approved provider copy, the system shall store exact maker/checker authorization, baseline comparison, single-dispatch state, provider readback, uncertain-effect recovery and trial linkage without inferring measured lift. [MV2]
- When `ONE_INSTALL` starts a fresh supported installation, the system shall return a usable workspace to a nontechnical owner after one installation without terminal commands while preserving protected credentials and approval boundaries. [MV3]
- When `WIZEME_TRIAL` compares its preregistered baseline and follow-up, the system shall emit observed metric counts, denominators, windows, source receipts and uncertainty including negative unchanged or inconclusive results without substituting fixture or benchmark evidence. [MV4]
- When `LINUX_CI` verifies a candidate, the system shall discover the same Python and Node suites as Windows, execute applicable native dependencies and retain named unsupported profile gaps without silently omitting failures. [MV5]
- While `TRIAL_PRIORITY` is active, the system shall reject unrelated feature and operation-catalog expansion while preserving all existing requirements and permitting narrowly necessary trial work, correctness repairs and required platform parity. [MV6]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Live source
 Given LIVE_READ has authorized app-scoped credentials
 When LIVE_READ refreshes and later loses permission
 Then MV1 retains dated observations and explicit failure recovery
Scenario: Provider execution
 Given GOVERNED_EXECUTION has an exact maker and distinct checker receipt
 When GOVERNED_EXECUTION loses its write response
 Then MV2 reconciles provider state without duplicate dispatch
Scenario: Installation
 Given ONE_INSTALL has a fresh declared platform
 When ONE_INSTALL is performed by a nontechnical owner
 Then MV3 reaches a usable workspace without terminal instructions
Scenario: Honest results
 Given WIZEME_TRIAL has a preregistered metric and dated baseline
 When WIZEME_TRIAL observes no detectable improvement
 Then MV4 records the actual result and uncertainty
Scenario: Platform verification
 Given LINUX_CI has the candidate source and declared native dependencies
 When LINUX_CI discovers and executes the shared suite inventory
 Then MV5 retains actual platform results and named missing profiles
Scenario: Scope priority
 Given TRIAL_PRIORITY is active
 When TRIAL_PRIORITY reviews proposed unrelated catalog expansion
 Then MV6 keeps the trial ahead of feature-count milestones
```

Implementation/acceptance contract: docs/MARKETER-COMPLETION-GATES.md.
This adds no authorization for a live provider send, spend, publication or activation.
