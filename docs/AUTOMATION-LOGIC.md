# Automation logic: facts → rules → proposals

Status: **P0 evaluator, P1 fact projection/simulation UI and immutable rule versions implemented; persistent proposal inbox, cooldowns across runs and scheduling are not.**

## Principle

The user writes policy; WMM evaluates saved facts and produces **proposals**. Effects still require the existing exact approval or an already-authorized bounded grant. Missing data never becomes a match, and no rule can invent a result.

```
saved facts ──> rule evaluation ──> proposal + reason ──> human/agent decision ──> existing approval ──> receipt
```

## User inputs

### Goal contract

- one objective and primary metric;
- baseline or explicit unknown;
- observation window, maturity and stop rule;
- allowed channels/tools;
- budget ceiling, default zero;
- approval mode: `PROPOSE_ONLY` (default) or `AUTO_WITHIN_GRANT`.

### Rule

```json
{
  "id": "coverage-repair",
  "enabled": true,
  "priority": 20,
  "when": {
    "all": [
      {"fact": "study.window.state", "op": "eq", "value": "ENDED"},
      {"fact": "study.coverage", "op": "ne", "value": "COMPLETE"}
    ]
  },
  "then": {
    "propose": {
      "action": "repair_coverage",
      "tool": "install.import.preview",
      "reason": "The study window ended but coverage is incomplete."
    },
    "requires": ["EXACT_APPROVAL"]
  },
  "cooldown": "P1D",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

Rules support:

- `all`, `any`, `not`;
- comparisons: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`, `exists`, `missing`;
- typed facts with units and timestamps;
- optional persistence (`for`) and cooldowns;
- priority and stable ordering;
- `unknown_policy`: `DO_NOT_FIRE` (default) or `PROPOSE_DATA_REPAIR`.

## Fact model

Facts are read-only projections of saved state:

- app/release/locale/currency/goal;
- study status, window, events, coverage;
- install counts by state and day view;
- cohort/retention maturity and availability;
- experiment state and decision;
- provider health, exceptions, jobs and approvals;
- current grants and remaining authority;
- current time in the declared timezone.

Every fact carries `source`, `observed_at`, `value`, `unit` and `status`. Missing/partial/stale facts are explicit. There is no inferred D7 retention, no engagement-as-install and no blended ROI.

## Evaluation semantics

For each rule, in priority order:

1. Resolve facts against the current app version/hash.
2. Evaluate booleans with three-valued logic (`TRUE`, `FALSE`, `UNKNOWN`).
3. A rule fires only on `TRUE`; `UNKNOWN` produces a data-repair proposal only if configured.
4. Apply persistence/cooldown/deduplication.
5. Validate the proposed action against the operation catalog and current authority.
6. Emit a proposal with fact snapshot hash, rule version/hash, reason and required approvals.

No model call is required. An optional agent may explain or suggest rules, but cannot silently activate them.

## Proposals

A proposal is **not** an execution:

- `PROPOSED` → owner/agent reviews;
- `ACCEPTED` → existing approval path;
- `REJECTED` / `EXPIRED` / `SUPERSEDED`;
- `EXECUTED` only after the existing receipt exists.

Proposals deduplicate by rule + fact snapshot + action. Conflicting proposals surface both reasons; priority never overrides an approval.

## Authority

- Default is `PROPOSE_ONLY`.
- `AUTO_WITHIN_GRANT` can only use operations already in an active owner grant and still respects expiry, quota, app version and review state.
- Publish, spend, external messages and policy changes always need exact approval.
- A rule cannot approve itself, raise its own budget or extend a grant.

## User experience

- **Builder:** “When [fact] [operator] [value] and [fact], propose [action].”
- **Advanced:** edit JSON with schema validation.
- **Simulation:** run against saved facts without writing; show why it fired, why not, or what is unknown.
- **Impact preview:** list actions and approvals a rule could request.
- **Agent handoff:** an agent can propose a rule; the owner edits and approves its version.
- **Explainability:** every proposal links to the fact snapshot and rule hash.

## Audit

Retain rule version/hash, evaluator version, evaluation time, fact snapshot hash, decision, approver/grant, execution receipt and any unknown states. The audit bundle should include rule and proposal counts/digests.

## Metrics

- proposals accepted/rejected;
- false-positive and data-repair proposals;
- time from proposal to decision;
- blocked actions and unknown-fact rate;
- no claim of time saved or growth without measurement.

## P0 usage

```sh
python -m mission_control.automation_rules \
  --rules docs/automation-rules.example.json \
  --facts facts.json
```

`facts.json` is a read-only snapshot of typed values. The evaluator validates the rules, returns `MATCH` / `NO_MATCH` / `UNKNOWN` / `EXPIRED` / `DISABLED`, and emits proposals only. It never writes, calls a provider or approves an action.

Against a local workspace database:

```sh
python -m mission_control.automation_rules \
  --rules docs/automation-rules.example.json \
  --database <owner-private>/mission-control.sqlite3 \
  --app <app-id>
```

The database mode opens an existing WMM database read-only and scopes one snapshot to the selected app. It reads saved app details, cohort and retention record counts, the number of campaigns with saved import batches, and local experiment counts. It does not initialize a database, seed workspaces, load credentials, or execute any proposal.

The bundled cohort-setup rule proposes an owner review when the workspace has no saved cohort metric records. That zero is a local record count. Study coverage, retention maturity, and unavailable measurements remain unknown unless supplied explicitly in `--facts`.

## Simulation UI

In **Review results**, app owners can open **Automation rules**. The starter rule suggests reviewing measurement setup when the app has no saved cohort metrics. Preview another rule by editing the JSON. Missing evidence is listed separately from rules that did not match.

The preview checks the current local owner session and checks app membership in the same read-only database snapshot as the facts. It does not call providers or create approvals. **Save rules** appends an immutable owner-authored version; saving writes only the rule set, while evaluation still creates no approval or effect. A response is discarded if its panel or app context changes before it arrives.

## Delivery phases

1. **P0 (implemented):** deterministic evaluator + validation + simulation + tests.
2. **P1 (projection and simulation UI implemented; inbox pending):** typed fact projection, owner rule simulation and proposal inbox.
3. **P2 (rule versions implemented; inbox/schedule pending):** scheduled evaluation, proposal inbox, cooldown store and deduplication across runs.
4. **P3:** agent-suggested rules and explanations, never auto-activation.

This design preserves the validation-first scope in [ADR 0002](adr/0002-stay-narrow.md).
