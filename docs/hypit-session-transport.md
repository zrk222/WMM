# Protected Studio transport checkpoint

The local server owns one Studio manager shared by human HTTP, CLI and MCP
operations: plan, start, sessions, read, edit, inspect and close. Client processes
do not own native sessions. Human access requires exact local origin, route,
framing, CSRF and fresh OWNER identity. Agent access uses current scoped grants
and the existing maker/checker review path.

An uncertain native effect remains UNKNOWN through HTTP, CLI and MCP. Repeating
a retained uncertain edit does not resend it. Server close retains confirmed or
unresolved owned cleanup. Studio descriptors are mapped to the existing video
workflow; they do not expand standing local-evidence approval. Complete standing
video automation remains blocked until its full workflow is implemented.

## Current local validation, 2026-10-25

- Clean Python 3.11 / MCP 1.30 full regression: 1,380 tests pass with unchanged
  source hashes and no skips. All 79 JavaScript tests pass.
- Focused transport/catalog/client/standing-policy coverage: 65 tests pass.
- Three deliberate code mutations fail and are restored. Exact target and empty
  or duplicate Transfer-Encoding rejection have additional negative coverage.
- Installed Hypit lifecycle: owner HTTP startup, CLI read, agent edit, retry
  without another send, official MCP readback and owned shutdown pass using a
  synthetic provider identity response and a real local authenticated session.
- SpecLine strict, validator mutation, task and drift checks pass. Forge
  architecture, reverse test verification and smoke pass. Forge QA covers the
  new route module, with maximum complexity 6; this is not a whole-code score.

Evidence is retained privately under .factory/hypit-session-transport and
.factory/studio-transport-full-regression; operational fixtures are not shipped.

## Open validation and product requirements

CF validation remains INCOMPLETE. Its bounded guard-path analyzer cannot prove
assigned identity checks and context managers. The broader Python security scan
covers 388 files with no pattern findings but retains 107 database-analysis gaps
and a missing tenant-read contract. These are coverage limits, not security
approval. Astra identified route/framing edge cases that are repaired and tested;
the final independent verdict is pending because the reviewer hit its usage limit.

This is a tested local checkpoint, not release or merge approval. Public restart
reconciliation, complete human Studio controls and preview isolation, full
Hypit/OpenCut editing/export workflows, and the other parent goal requirements
remain unfinished. No provider publication, spending or private production
activation was performed. Synthetic identities and local tests do not establish
live provider, customer or device acceptance.
