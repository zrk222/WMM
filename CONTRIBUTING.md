# Contributing to WMM

Start with [the contributor boundaries](AGENTS.md) and the
[workspace guide](docs/workspace-guide.md). Use a clean checkout and synthetic
fixtures. Core checks need no live provider account or credentials.

```sh
git rev-parse HEAD
python tools/test.py --profile inventory
python tools/test.py --profile core --install
python tools/test.py --profile node
```

Use the [maintainability guide](docs/MAINTAINABILITY.md) for style checks and architecture acceptance criteria.
Use the [test profile guide](docs/TESTING.md) for OS prerequisites and browser
checks. For a PR, record the full head SHA, environment, commands, results,
and any skips or untested surfaces. Include a reproduction command and the
expected behavior for each material change.

## Review and handoff

WMM currently has one repository maintainer. Follow the existing
[owner review policy](docs/REVIEW-POLICY.md) for the local preview. A separate
agent, green CI, or the owner's own review cannot establish independent human
review. If no independent reviewer has submitted findings for the current
candidate, record **Independent review pending**.

Ask a human who did not author or direct the change to inspect the diff and
reproduce the relevant checks from a clean checkout of the exact PR head.
Ask them to record the reviewed SHA, scope, checks and results, findings,
and disposition in the PR. A changed head needs review of the new changes
and an updated review record. Use the [security review packet](docs/SECURITY-REVIEW-PACKET.md)
as a scope reference and refresh its candidate before relying on it. Independent
security review is required for the expansion cases listed in the owner policy.

Keep the handoff in the PR: what changed, how to reproduce it, outstanding
risks, and the next action. Never put operational credentials or private
provider evidence in the handoff.

## Evidence and repository size

Keep compact contracts, reproducible fixtures, and non-sensitive proof
receipts in Git. Keep bulky generated logs, scans, build outputs, and
repeated snapshots outside Git. Do not force-add ignored output. An
exception needs a reason, an owner, and a link to the PR that approved it.

Before retiring an existing tracked proof input, identify its readers,
preserve the original bytes in durable storage with appropriate access,
and record the candidate SHA, artifact SHA-256, stable retrieval location,
and verification command. Verify retrieval and replay before removing
the tracked copy. Check repository history and access before assuming a
deleted file is gone.
