# Lean WMM process and implementation

User-authorized scope: streamline the complete WMM process while preserving every
requested functional workflow, app isolation, current evidence and approval scope.
This is added to the active gap-closure and upgrade goal.

## Measured starting point

A five-read Windows/Python3.11 synthetic three-app workspace profile records
0.399–0.546 seconds per workspace read, a149,010-byte serialized response,
1,285 SQLite execute calls and260 Store.app calls across five reads. These are
local synthetic observations, not production latency or measured savings.
Exact profiler evidence is `.factory/progressive-workflow/workspace-baseline.json`.

## Required optimization work

1. Profile realistic small, medium and large app/history fixtures with exact source
   hashes. Record cold/warm p50/p95, response bytes, SQL/read counts and browser
   render/input timing before setting acceptance thresholds.
2. Consolidate repeated workspace reads into a bounded read projection where it
   preserves current transactional semantics. Never cache authorization, source
   freshness or mutation admission. Compare concurrent-writer behavior explicitly.
3. Reuse the existing guided workflow, weekly portfolio and snapshot machinery.
   Extend their domain projections rather than introducing parallel versions.
4. Consolidate strict framing, error classification, dialog focus and stale-response
   handling through shared helpers only after proving route-specific limits and
   authority remain exact. Preserve UNKNOWN from server through CLI/MCP/UI.
5. Page unified history and portfolio queries; request detailed source payloads only
   when needed. Keep explicit coverage and unavailable states. Never suppress open
   critical findings to make a page look simpler.
6. Keep operation schemas and effect metadata authoritative for discovery, clients
   and UI actions. Minimize duplicated adapters while retaining distinct human
   approval and agent execution identities.
7. Replace redundant full-suite runs with scoped, hash-current checks during active
   edits; run full regression on a frozen candidate before acceptance. A drifted
   run is diagnostic and cannot become a current pass.

Each change needs an exact before/after benchmark on the same workload, meaningful
failure/concurrency tests and applicable CF workflow proof. Remove redundant work
only when these show preserved correctness. No speed, token, cost or quality-score
improvement is claimed until measured. The new progressive workflow view is the
first presentation change; broader code/process optimization remains in progress.
