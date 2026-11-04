# Plan: commercial-growth-operations
Spec: specs/commercial-growth-operations.md
Architect verdict: CONCERNS

Owner accepted these additions as remaining goal criteria on November 4, 2026.
This plan does not certify the requirements implemented. Tenant architecture,
provider contracts and live test accounts require concrete evidence before the
corresponding release claims. Existing goal requirements remain unchanged.

## Logical decomposition (phases)
1. Finish the current organic-video integration, exact owner execution path,
   scheduled recovery, measurement and original setup acceptance.
2. Design tenant and client isolation, generic sign-in, team roles and an
   explicitly chosen hosted credential/execution boundary before cloud release.
3. Deliver hosted first-value onboarding with a sample journey, then actual
   owner connection and exception-driven automation; validate with a new user.
4. Add business-aware manifests, goal templates and measurements while retaining
   existing app workflows and stable internal identifiers.
5. Complete and verify network adapters individually, starting with existing
   Meta and required Instagram, TikTok and YouTube flows. Add LinkedIn and the
   declared paid networks using their own authority and recovery contracts.
6. Prove the recurring outcome/report loop on real permitted businesses and
   disclose inconclusive outcomes. Compare tools only with measured evidence.

## Tasks (atomic — each independently shippable)
<!-- Rules enforced by `specline tasks`: one slice each, <=4 files,
     explicit verify command, no forward references. -->
- [ ] T1 | slice=specs | files=specs/hosted-tenancy.md,specs/commercial-growth-operations.md | verify=`specline validate commercial-growth-operations` | Specify actual tenant/session/client boundaries, team roles, credential residency, migration/rollback and operation transport threat model before backend implementation.

## Required implementation packets

After T1 architecture review, split each phase into exact atomic source/test
packets before editing. Do not use a passing documentation validator as proof
of a hosted server, new provider adapter or business workflow. The acceptance
matrix below must be updated from actual implementation/test/live receipts.

| Requirement | Current acceptance state | Required proof |
| --- | --- | --- |
| Shared hosted team dashboard and isolation | NOT_IMPLEMENTED | Two tenants, four roles, cross-tenant rejection, revocation and audit receipts |
| Zero local setup SaaS | NOT_IMPLEMENTED | First-time operator completes a useful task, timed; reconnect/restart/recovery and mobile/keyboard checks |
| Cloud credential residency | DESIGN_REQUIRED | Opt-in onboarding/migration, protected storage, tenant-negative tests, no secrets in logs/artifacts |
| Broad organic networks | PARTIAL_BACKEND / MOST_PUBLISHERS_UNIMPLEMENTED | Per-network transport, recovery, permission and actual publication/status receipts |
| Paid network expansion | META_ENGAGEMENT_ONLY; OTHERS_UNIMPLEMENTED | Exact approved test effects, finite budgets, reconciliation and verified provider stop per adapter |
| App / commerce / services / content journeys | APP_FRAMING_CURRENT; OTHERS_UNIMPLEMENTED | Four appropriate first-value and measurement journeys without fabricated app-only fields |
| Exception-driven unattended operation | EXISTING_META_PARTIAL_LIVE; NEW_NETWORKS_PENDING | Browser closed, worker restart, no duplicate effect, actionable exception and receipt-backed owner report |
| Measured marketing benefit | NOT_ESTABLISHED | Dated source baseline/follow-up, sample sizes, costs, attribution limits and honest decision |

No new hosted engine is approved by a plan label. Reuse domain services, specify
the execution boundary and then prove it with integration and live acceptance.
