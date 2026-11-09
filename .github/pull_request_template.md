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
- [ ] The owner review is sufficient; no separate non-author reviewer is required.

## Boundary

- [ ] This change does not claim measured growth, provider delivery or causal
      lift without receipts.

## Notes for the reviewer

<!-- Anything surprising, risky, or deliberately out of scope. -->
