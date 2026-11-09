## What changed

<!-- One or two sentences. Link the issue or ADR if there is one. -->

## Verification

- [ ] I ran the relevant tests locally or in CI (list them).
- [ ] I did not add secrets, real customer data, tokens or private receipts.
- [ ] If this touches authority, credentials, budgets, attribution or release
      paths, I requested a reviewer other than myself.

## Security-sensitive review (required for listed paths)

Paths: `mission_control/**`, `.github/**`, `packaging/**`, `ios/**`,
`tools/*installer*`, `tools/*release*`, `LICENSE`, `SECURITY.md`,
`docs/SERVER-ENFORCEMENT-AUDIT.md`, `docs/REVIEW-POLICY.md`.

- [ ] A second human reviewer is named here: `@`
- [ ] The reviewer checked server-side authority, secret handling, exact-field
      validation, expiry/quota/budget enforcement and denial tests.
- [ ] No self-merge for these paths.

## Boundary

- [ ] This change does not claim measured growth, provider delivery or causal
      lift without receipts.

## Notes for the reviewer

<!-- Anything surprising, risky, or deliberately out of scope. -->
