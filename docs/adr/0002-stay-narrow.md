# ADR 0002: Stay narrow until verified value

- **Status:** Proposed by engineering, for owner acceptance.
- **Date:** 2026-11-09
- **Owners:** Product/owner

## Context

The measurement path is built and passes synthetically: tagged study, exact post
approval, install import, study link and day 1/3/7 reporting. There is still no
measured result from the WizeMe trial, and no independent founder test has shown
that a cold user reaches a first useful packet.

Under that condition, adding scope is speculation:

- a live MMP connector needs a real manual export first;
- a hosted team service needs sessions, HTTPS transport, a member UI and an
  identity-provider decision;
- more ad networks and agent personas create support and security obligations;
- more dashboards do not produce evidence.

## Decision

**Stay narrow until verified value is recorded.**

Until the gates below are met, do not build:

- a live MMP/attribution connector;
- additional paid ad networks or install-optimized paid execution;
- the hosted multi-user team service (sessions and invitations may stay as
  primitives);
- new agent personas or additional analytics dashboards;
- a broad video editor or iOS expansion.

## Gates to revisit

All of these should be true:

1. One real tagged campaign produced a source-backed report with linked
   landings/registrations and, if available, installs; incomplete coverage is
   explicitly marked.
2. The decision (`CONTINUE`, `REVISE`, `COLLECT`, or `STOP`) is recorded with
   receipts, even if the result is null or inconclusive.
3. At least 4 of 5 independent founders prepare a useful first packet without
   developer intervention; at least 3 choose to use it again.
4. A specific commercial scope and price is confirmed by two prospective buyers.

## Consequences

- Positive: effort stays on proof and first-value friction, not surface area.
- Negative: teams wanting hosted multi-user, live connectors or more networks
  wait. That is intentional.
- Revisit when the gates pass; the ADRs and runbook already describe the next
  steps.

## Relation to existing decisions

- [ADR 0001](0001-team-tier.md) still defines the eventual team architecture.
- The measurement runbook defines how to produce gate 1.
- Owner review policy governs changes; no second reviewer is a blocker.
