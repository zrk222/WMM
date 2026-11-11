## What changed

<!-- One or two sentences. Link the issue or ADR if there is one. -->

## Verification

- [ ] I ran the relevant tests locally or in CI (list them).
- [ ] I did not add secrets, real customer data, tokens or private receipts.
- [ ] If this touches authority, credentials, budgets, attribution or release
      paths, I ran the owner security review checklist below.

## Security-sensitive owner review (required for listed paths)

Paths: `mission_control/**`, `.github/**`, `packaging/**`, `ios/**`,
`tools/*installer*`, `tools/*release*`, `LICENSE`, `SECURITY.md`,
`docs/SERVER-ENFORCEMENT-AUDIT.md`, `docs/REVIEW-POLICY.md`.

- [ ] I reviewed this change as the repository owner.
- [ ] I checked server-side authority, secret handling, exact-field validation,
      expiry/quota/budget enforcement and denial tests.
- [ ] I applied the owner review policy and its expansion gate.

## Boundary

- [ ] This change does not claim measured growth, provider delivery or causal
      lift without receipts.

## Notes for the reviewer

<!-- Record the head SHA, environment, reproduction steps, and any limits. Link an independent review of this head or state 'Independent review pending'. See ../CONTRIBUTING.md for the protocol. -->
