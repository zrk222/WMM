# Spec: viral-discovery-policy
Status: draft

## MUST - Functional core
### Description
Implement the user-selected deterministic admission rule for the viral-only discovery queue. A candidate needs at least 100000 observed views and at least ten times the median views of comparable recent prior creator posts. This policy consumes already collected observations; collection, scheduling, editing and human approval remain separate required workstreams.

### Requirements (EARS)
- The system shall compute the creator baseline from 10 through 20 distinct prior posts matching candidate creator, platform and format while excluding the candidate through `creator_baseline`.
- The system shall return qualified only when observed candidate views are at least 100000 and at least ten times the exact median baseline views through `viral_cutoff`.
- The system shall return insufficient-baseline when fewer than 10 comparable prior posts remain and reject malformed, duplicate, future, mismatched or ambiguous observations through `observation_validation`.
- The system shall store candidate identity, selected baseline identities, source observation hashes, median, required views and exact qualification reasons in a deterministic receipt through `qualification_receipt`.
- The system shall return reference review required and publication not run independently of qualification without granting editing rights through `approval_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: creator_baseline
  Given comparable creator post observations
  When `creator_baseline` is computed
  Then candidate identity is excluded and the most recent eligible baseline posts are selected
Scenario: viral_cutoff
  Given the user's absolute and relative cutoff
  When `viral_cutoff` is evaluated
  Then both thresholds must pass including exact boundary values
Scenario: observation_validation
  Given missing baseline or malformed source observations
  When `observation_validation` is applied
  Then insufficient evidence cannot produce a qualified candidate
Scenario: qualification_receipt
  Given the same candidate and baseline observations
  When `qualification_receipt` is emitted
  Then ordering-independent source hashes and exact median calculations are retained
Scenario: approval_boundary
  Given a qualified candidate
  When `approval_boundary` is inspected
  Then source reuse and publication remain unapproved
```

## SHOULD - Technical
- Use exact integer/rational median arithmetic, never rounded multipliers to admit a borderline candidate.
- Platforms are TikTok, Facebook and Instagram. Use source identifiers and timestamps; do not infer paid/organic classification or missing view counts.
- The core policy is pure and performs no network, scheduling, download or provider mutation. Later adapters must verify collection permissions and freshness before queue admission.
- Baseline uses the most recent comparable prior posts supplied by a collector; a collector must demonstrate its inventory completeness before claiming the resulting median represents the creator. A cherry-picked subset is not verified typical performance.
- A zero median cannot establish a tenfold performance multiplier and returns insufficient-baseline. Bound supplied history to 1000 posts, identity text to 120 characters and reported views to integer values from zero through one trillion. No missing views are imputed.
- The parent UPG-09 remains incomplete until actual source discovery, scheduler, full shared editing controls and human/agent acceptance are implemented.

## Authorized parameters
MIN_VIEWS = 100000
MULTIPLIER = 10
MIN_BASELINE = 10
MAX_BASELINE = 20
MAX_OBSERVATIONS = 1000
MAX_VIEWS = 1000000000000
