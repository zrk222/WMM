# Security-sensitive review policy

## Requirement

Every security-sensitive change needs **one approving review from a human other
than the author** in addition to green CI. This is a process requirement; code
cannot create the second person.

Security-sensitive paths:

- `mission_control/**` (grants, authority, credentials, attribution, campaigns)
- `.github/**` (workflows, release and review gates)
- `packaging/**`, `tools/*installer*`, `tools/*release*`, `tools/publish_*`
- `ios/**` (native storage, Keychain, device identity)
- `LICENSE`, `SECURITY.md`, `docs/SERVER-ENFORCEMENT-AUDIT.md`, this file

## Current status

No second reviewer is configured. The repository owner must name one. Until then,
security-sensitive changes should be treated as unreviewed even when CI is green.

## How to enforce it

1. Name the second reviewer's GitHub handle.
2. Add `.github/CODEOWNERS`:

   ```
   * @OWNER_HANDLE @SECOND_REVIEWER_HANDLE
   /mission_control/ @SECOND_REVIEWER_HANDLE
   /.github/ @SECOND_REVIEWER_HANDLE
   /packaging/ @SECOND_REVIEWER_HANDLE
   /ios/ @SECOND_REVIEWER_HANDLE
   /LICENSE @SECOND_REVIEWER_HANDLE
   /SECURITY.md @SECOND_REVIEWER_HANDLE
   ```

3. In **Settings → Branches → main**, require:
   - a pull request before merging;
   - at least **1 approving review**;
   - **dismiss stale approvals** on new commits;
   - **require review from Code Owners**;
   - **do not allow the author to self-approve** (GitHub does this by default);
   - the existing required checks.
4. Keep CodeRabbit or another automated reviewer as an extra signal, never a
   substitute for the human review.

The CLI token used in this workspace can create PRs and checks but cannot
administer branch protection; steps 3 must be done by the repository admin in
GitHub settings.

## Review checklist

Use `.github/pull_request_template.md`. Reviewers should confirm:

- server-side authority is re-derived, not trusted from the body;
- no credential, token or private payload is logged, exported or returned;
- exact-key validation rejects unknown fields;
- expiry, quota, revocation and budget limits are enforced before effects;
- AGENT/HUMAN/PUBLIC_SOURCE origin is server-derived;
- tests cover the denial path, not just success;
- no measured result or provider outcome is claimed without receipts.

## Emergency changes

If a security fix must land before the reviewer is available, record the reason,
the exact change, the tests run and a follow-up review deadline in the PR. Do not
merge silently.
