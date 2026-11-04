# Spec: commercial-growth-operations
Status: owner-accepted requirements; architecture and implementation pending

## MUST — Functional core
### Description
Extend the active WMM goal with hosted collaboration, zero-install onboarding,
multi-network exception-driven operations, and dedicated app, e-commerce,
local-service and content-business journeys. These requirements supplement the
existing goal; they do not replace unfinished video, setup, authority or live
acceptance work. Acceptance added by the owner on November 4, 2026.

This document records required outcomes, not shipped capabilities. A connected
identity, source stub, plan, fixture, queued job or provider acknowledgement does
not establish supported execution or measured growth. "Set and forget" means
durable permitted work with actionable exceptions and owner reports, not a
growth guarantee or an unattended bypass of provider consent requirements.

### User roles
- Owner: selects business outcome, accounts, limits, roles and automation scope.
- Operator: prepares and runs only assigned workflows under current authority.
- Reviewer: independently reviews exact changes where the effect requires it.
- Viewer: reads permitted workspace dashboards without executing changes.
- Personal agent or agent team: uses the same enforced per-operation authority.

### Requirements (EARS)
- The system shall return a complete role-aware operational GUI for founders and teams through `operational_gui`, covering the supported workflow lifecycle without requiring terminal commands, YAML editing or raw API requests; the public sample shall not satisfy product acceptance.
- The system shall return tenant-scoped shared cloud dashboards and reject actions outside assigned team roles or client boundaries through `team_isolation`.
- When an operator changes a role, the system shall invalidate affected live grants, queued work and approvals through `role_revocation` without erasing receipts.
- The system shall provide a hosted browser journey from sign-in to a useful packet without a terminal, local Python, installer, GitHub developer identity or grant JSON editing through `zero_install`.
- Where an owner chooses hosted execution, the system shall reject credential migration without explicit consent and store onboarded credentials in protected tenant-scoped storage through `credential_residency`.
- When the owner approves automation, the system shall summarize agent/team, business, accounts, supported actions, exact content or tested variant policy, destinations, schedule, expiry, quotas, currency, budget and stop rules through `automation_agreement`.
- The system shall store effect receipts and provider readback for approved Facebook, Instagram, TikTok, YouTube Shorts and LinkedIn organic workflows, and paid Meta, Google Ads, TikTok Ads, LinkedIn Ads and Apple Search Ads acquisition through `network_operations` only for tested business/objective combinations and approved provider access.
- If a network requires creator interaction, missing permissions, review, payment approval or unavailable capability, the system shall show the specific required action and preserve safe progress through `actionable_exception`; it shall not label that network fully autonomous.
- When permitted automation runs, the system shall store schedules, leases, quotas, effect IDs, reconciliation and owner reports across browser/worker restarts through `unattended_recovery` without duplicate effects or blind replay of uncertain mutations.
- When a stop rule fires, the system shall stop new work and verify the supported provider pause through `protective_stop`; it shall preserve incurred charges and unresolved effects.
- The system shall return APP, ECOMMERCE, LOCAL_SERVICE and CONTENT journeys with business-specific readiness, destination, creative, experiment and measurement contracts through `business_journeys`; non-app businesses shall not need invented store IDs, app releases or install events.
- The system shall return observed KPIs for the selected business with sources, windows, denominators, costs and unavailable values through `business_measurement`, without treating views as sales or before/after differences as causal lift.
- The system shall return the existing local desktop path and accessible desktop/mobile controls as a deployment choice through `deployment_choice`; independent native iOS background execution shall not be assumed to be an always-on worker.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: operational_gui
  Given a founder or team operator using the actual WMM application
  When they onboard, connect accounts, prepare creative, review authority, run supported work, resolve exceptions and inspect results
  Then the GUI provides each role-appropriate action, current state, next step and receipt through the complete coverage contract in specs/commercial-gui.md without substituting sample data
Scenario: team_isolation
  Given two tenants and viewer, operator, reviewer and owner memberships
  When each identity reads dashboards or attempts effects in either tenant
  Then only explicitly assigned data and actions are available and cross-client data remains isolated
Scenario: role_revocation
  Given a queued operation and an exact current grant
  When the owner's role or that grant is revoked
  Then future effects stop and prior receipts remain readable to authorized owners
Scenario: zero_install
  Given a first-time nontechnical operator on a supported browser
  When they sign in, select their business and connect one account or use the labelled sample
  Then they obtain one useful packet without a terminal and their elapsed time and friction are recorded
Scenario: credential_residency
  Given credentials saved in a local private vault
  When the owner enables hosted operation
  Then no credentials move until explicit onboarding or migration approval is completed and verified
Scenario: automation_agreement
  Given supported workflows and the selected business accounts
  When the owner reviews the agreement
  Then exact effects, content policy, schedule, expiry, quotas, budget and stop rules are readable before activation
Scenario: network_operations
  Given separately authorized test accounts for each declared network adapter
  When approved work executes and a mutation response is interrupted
  Then dated provider readback and restart reconciliation prove that adapter's exact effects without duplicates
Scenario: actionable_exception
  Given a network requires a creator's privacy selection or fresh consent
  When an agent reaches that step
  Then the owner receives the exact preserved preview and required decision instead of a false automation success
Scenario: unattended_recovery
  Given approved scheduled work and an optional always-on runner
  When the browser closes and the runner restarts
  Then the same retained work continues or reconciles once and an owner report names completed and unresolved effects
Scenario: protective_stop
  Given a separately approved paid test with a stop threshold
  When the threshold is observed
  Then no new spend action is admitted and an actual provider readback verifies the supported pause
Scenario: business_journeys
  Given one real fixture for each of the four business types
  When an operator sets a goal and an agent prepares creative and an experiment
  Then each journey uses relevant destination and conversion events without fabricated app-only fields
Scenario: business_measurement
  Given partial source data for purchase, lead, subscriber or app conversion
  When the owner opens results
  Then observed metrics identify sources and denominators while missing or unattributed outcomes remain unknown
Scenario: deployment_choice
  Given a hosted or local owner and mobile or desktop viewport
  When they approve, monitor, recover or export work
  Then keyboard/focus and responsive acceptance pass and credentials remain in the selected execution environment
```

## SHOULD — Technical/structural
- Reuse the existing domain services, CLI/MCP envelopes, exact operation guards,
  policy and campaign scopes, durable jobs, media, analytics and owner reports.
- Review a tenant/authentication architecture before exposing hosted execution;
  the current loopback server is not a multi-tenant SaaS server.
- Keep stable internal app identifiers compatible while adding business type and
  business-specific presentation/validation. Do not rename every DB table merely
  to remove app-centric wording.
- Map agency/client boundaries explicitly. Portfolio aggregation is opt-in and
  authorized; team membership alone never grants cross-client access.
- Preserve distinct reviewer identity where required. Do not replace approval
  gates with a cosmetic toggle or a role name.
- Each network needs its own operation/capability, permission, content, cost,
  recovery and measurement tests, plus dated live receipts before support claims.
- Paid tiers and paid-provider consumption remain explicit owner choices with
  current prices, quotas and budget approval; a free tier is not unlimited usage.
- App KPIs: installs/activation, store conversion, mature retention and eligible
  revenue/acquisition economics. Commerce: purchases, refunds, margin and ROAS.
  Services: qualified leads, appointments, attendance and conversion. Content:
  attributable subscribers, engaged audience and eligible paid conversion.
- Use source-bound evidence; do not guarantee growth or declare competitive
  superiority without an appropriate comparative benchmark.

## SHOULD NOT — Implementation details
No silent migration of private owner accounts into a shared public integration.
No broad paid activation or live publication follows from accepting this spec.
No external outreach, new vendor payment or production deployment is executed
by recording these requirements. Prepare concrete reviewable work first.

## Architecture review still required
Extract typed tenant, business, effect, consent and evidence facts during T1
before compiling decision rules. Requirement acceptance does not constitute
an architecture approval or implementation gate for the new hosted surface.
