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

Green CI and a GitHub approval from the configured independent reviewer are
required. The `Independent human review` check uses the owner's configured
GitHub account ID and the exact PR head. It rejects missing, stale, dismissed,
self, and other-account approvals. An ordinary comment is not a decision.

Keep the owner-only main update rule in effect. `CODEOWNERS` routes stewardship;
do not require a separate native code-owner approval while the owner is the only
code owner. GitHub requires write access to be a code owner. An independent
reviewer can use the configured check with read access and does not receive
merge or release authority.

Once the independent check is on main and has been verified on a PR, add its
GitHub Actions status to the main ruleset and read the settings back. Until then
the owner must verify the actual approving review on the exact head before
merging. If a valid independent decision is missing, leave the PR open.
`docs/OWNERSHIP.md` records the separate second-maintainer onboarding.

## Residual risk and expansion gate

Owner-only review can document an existing local preview. It does not provide
independent assurance or satisfy this policy. Before enabling remote team access, a hosted
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
