# Dependency freshness and advisory scope

Native Dependabot proposes grouped weekly pip updates for `/` and `/docs`, npm
updates for the root lock, and GitHub action updates. Each ecosystem allows two
open update PRs. Proposals require review and normal checks; nothing auto-merges.
Exact versions, action SHAs, requirement hashes and npm integrity fields remain
required. The small helper lives in `tools/`; it adds no production runtime code.

The weekly/manual Dependency freshness workflow installs the hash-locked
`docs/requirements-audit.txt` tool profile, then runs strict pip-audit with
required hashes against `requirements.txt`, `docs/requirements-dev.txt`, and
`docs/requirements-properties.txt`. A separate job runs `npm ci --ignore-scripts`
and `npm audit --json`. Reports, stderr and actual exit statuses are retained
even on failure. Vulnerabilities, advisory-service errors, missing hashes or
installation errors fail the job; NOT_RUN evidence never means a clean audit.

This is known-advisory checking for the declared profiles on Ubuntu/Python 3.11,
including platform-marker filtering. Windows-only requirements and optional
browser, provider, packaging and native dependency profiles are outside that
audit run. It does not assess malware, license suitability, undeclared packages,
FFmpeg contents, operating-system packages or the full supply chain.

The audit tool was selected from the official PyPI JSON metadata. To regenerate
its exact universal, wheel-only transitive lock after reviewing a tool update:

```sh
uv pip compile docs/requirements-audit.in --universal --generate-hashes --only-binary :all: --python-version 3.11 --output-file docs/requirements-audit.txt
```

FFmpeg proposals read only the official `GyanD/codexffmpeg` latest stable release
metadata. The helper requires the exact matching version, filename, versioned
GitHub URL and provider `sha256:` asset digest. It downloads no binary. Missing
digest evidence, downgrades, same-version hash changes, or unrelated workflow job
baseline drift stop preparation. Updates change only `tools/ffmpeg-pin.json`;
workflow and CI-baseline bytes remain untouched. Its closed schema permits only
a stable version and lowercase SHA256. Windows checks validate this data through
the helper before parsing JSON, construct the fixed official versioned URL, and
retain the existing download/hash/execution checks. Failed pin readback restores
the original data. Receipts bind the before/after data hashes.

Only trusted main runs may propose changes. The workflow skips an existing open
`codex/deps-ffmpeg-*` proposal and otherwise creates a unique run branch. An empty
expected-SHA push lease permits creating that ref only; existing branches cannot
be overwritten. Git uses the fixed `gh` credential helper, with no token in push
arguments. Contents, pull-request and action permissions support the data-only
push, PR creation and explicit check dispatch. Future FFmpeg proposals do not
edit workflow files or need a broader Workflows-capable credential. Repository
policies can still reject a push or PR; those outcomes remain failures.

A GITHUB_TOKEN-created PR is not assumed to trigger CI. After creating it, the
workflow explicitly dispatches `checks.yml` on the new branch with the exact
checked-out main `base_sha`. The ordinary source ratchet validates the 40-hex
base and all normal jobs run. A failed dispatch leaves an unverified proposal;
it grants no merge waiver. Metadata and update receipts are retained. Source
tests do not prove the scheduled workflow has run or that current advisories are
clear; hosted execution and successful check evidence remain separate.
