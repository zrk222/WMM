# Security-sensitive review policy

## Requirement

Every security-sensitive change needs **owner review** and green CI before merge.
The repository owner is the reviewer. A separate non-author reviewer is not
required and is not a merge blocker.

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

Green CI is required. Do **not** enable “require approvals” while the owner is
also the only author: GitHub does not allow self-approval, so it would block work
without adding a reviewer.

If a second human becomes available later, CODEOWNERS and required approvals can
be added as an optional strengthening. That is a future choice, not a current
blocker.

## Emergency changes

Record the reason, the exact change and the tests run in the PR. The owner review
checklist still applies.
