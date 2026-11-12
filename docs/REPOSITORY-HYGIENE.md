# Repository branch hygiene

The weekly GitHub workflow plans and deletes only stale `codex/*` branches in
`zrk222/WMM`. Manual dispatch defaults to `dry_run: true`; disable that option to
apply the same guarded cleanup. A shallow checkout supplies local worktree
exclusions; branch and PR inventories come from paginated GitHub APIs, without a
full-history fetch or clone.

Eligibility requires all of the following:

- A single safe `codex/` branch suffix, an unprotected branch, and no open PR.
- No local active worktree on that branch. A hosted runner can observe only its
  own worktrees; it cannot discover developer worktrees on other machines.
- A closed PR merged into this repository's `main`, with the source branch and
  exact current source head SHA matching the branch. Squash merges qualify;
  ancestry of the squash commit is not used as source-head proof.
- Both the PR merge and source-head commit are strictly older than seven days.

`python tools/branch_hygiene.py plan` writes
`.factory/branch-hygiene/manifest.json` before mutation. The workflow must upload
that manifest successfully before its apply step can run. A manual dry run stops
after planning and upload. The manifest contains only repository and branch
identities, SHAs, PR numbers, timestamps, and exclusion reasons; never tokens,
credential responses, or customer content.

`python tools/branch_hygiene.py apply` reloads and validates the manifest, requires
the exact repository/schema and a manifest no older than one hour, and rechecks
GitHub repository identity, branch protection, the current head, current open
PRs, the exact merged PR, source commit age, and active local worktrees. Invalid
or changed eligibility skips deletion. Provider failures are recorded per
branch, allowing later candidates to be checked. The results include the manifest
SHA256 and actual `deleted`, `skipped`, or `failed` outcomes. A failed deletion
request can have an uncertain outcome; it must not be replayed without fresh
provider inspection and a new plan.

GitHub's DELETE ref API has no atomic expected-SHA precondition. The final fresh
head/protection read narrows the race before DELETE, but neither SHA comparison
nor the combined eligibility checks are atomic with deletion. A concurrent push,
PR creation, protection change, or worktree change can still race those reads.
The workflow serializes its own cleanup runs; it cannot lock other writers.
Receipts do not prove a target branch count or eliminate this provider limit.

No cleanup is performed on local working directories, unmerged branches, main,
non-agent branches, or other repositories. Local execution uses the current
`gh` authentication and never prints provider error bodies or `GH_TOKEN`.
