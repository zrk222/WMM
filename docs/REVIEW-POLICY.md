# Security-sensitive review policy

## Requirement

Every change to `main` needs **independent human review** and green CI before
merge. The reviewer must be a human who did not author or direct the change. The
author cannot approve their own pull request. Agent reviews, agent personas, CI
and owner self-review are evidence only; none counts as independent review.

Security-sensitive paths:

- `mission_control/**` (grants, authority, credentials, attribution, campaigns)
- `.github/**` (workflows, release and review gates)
- `packaging/**`, `tools/*installer*`, `tools/*release*`, `tools/publish_*`
- `ios/**` (native storage, Keychain, device identity)
- `LICENSE`, `SECURITY.md`, `docs/SERVER-ENFORCEMENT-AUDIT.md`, this file

## Owner review checklist

Before merging a security-sensitive change, the owner should confirm:

- server-side authority is re-derived, not trusted from the body;
- no credential, token or private payload is logged, exported or returned;
- exact-key validation rejects unknown fields;
- expiry, quota, revocation and budget limits are enforced before effects;
- AGENT/HUMAN/PUBLIC_SOURCE origin is server-derived;
- tests cover the denial path, not just success;
- no measured result or provider outcome is claimed without receipts.

Use `.github/pull_request_template.md` to record the check.

## Enforcement

Green CI, a code-owner approval and the `Independent human review` check are
required. Branch protection must require approvals and code-owner review; the
workflow fails when no non-author human has approved the exact PR head.

The author cannot merge around a missing review. If no second human is available,
the change waits. `docs/OWNERSHIP.md` records the bus-factor gap and the required
second-maintainer onboarding.

## Residual risk and expansion gate

Owner-only review is accepted for the current local, single-owner preview. It does
not provide independent assurance. Before enabling remote team access, a hosted
tenant service, materially expanded paid execution or commercial delivery, require
an independent security review covering the combined session, membership, HTTPS,
revocation and tenant boundary. Record the reviewer, scope, findings and disposition
in the PR. See [TEAM-SESSION-SECURITY-REVIEW.md](TEAM-SESSION-SECURITY-REVIEW.md).

## Documentation accuracy

Security-relevant operator docs must describe the shipped interface. The install
import preview/confirm UI is shipped; the measurement runbook points to it first and
keeps the CLI as a headless fallback. Do not restore a "not shipped" warning without
checking the current UI and tests.

## Emergency changes

Record the reason, the exact change and the tests run in the PR. The owner review
checklist still applies.
