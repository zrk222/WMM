# Dashboard module migration and maintenance audit

Scope: the DeepSeek maintenance/extraction series through `c2fd1fb`, followed by
the native dashboard module migration. This is a bounded engineering review,
not a claim that every historical change or product workflow is defect-free.

## Changes

The dashboard now starts from `dashboard.mjs`. Its 45 controllers declare their
imports and exports; `app.mjs` owns state and starts once after linkage.
`feature-apis.mjs` retains 27 existing feature-library compatibility APIs.
Callback pages keep their separate scripts. No bundler or runtime dependency
was added. The server retains an exact asset allowlist.

ESLint rejects undeclared identifiers and imported-binding assignment. The graph
check uses Node's native parser/linker without evaluating app code; it covers
static import/re-export forms and rejects dynamic dependencies. Browser tests
remain separate evidence for actual DOM behavior and module evaluation. Legacy
VM unit tests use a source adapter only for isolated functions, not linkage proof.

## Findings and fixes

- Backend Architect reproduced an older runtime accepting a future migration
  ledger and lowering `user_version`. Unknown versions and conflicting names
  now fail before adoption/version writes. Regression assertions fail against
  the original implementation and pass with the fix.
- Migration testing caught missing status-renderer imports and the publication
  API binding; explicit imports now replace those implicit globals.
- EGM identified incomplete regex import detection. Native linkage replaced it;
  fixtures cover missing dependencies/exports, indented and same-line imports,
  namespace/default imports, re-exports and rejected dynamic imports.
- Browser harnesses now import state explicitly. Polling uses synchronous
  predicates with module-state handles; isolated synthetic fixtures retain their
  own local state. Report/weekly tests follow the current goal-first disclosure.

## Verification

Local Windows/Python 3.11/Node 22 checks include all Node tests, migration and
HTTP asset tests, lint/format checks, actual Chromium desktop/mobile owner
approval/revocation/scheduling flows, publication/research/error recovery,
weekly exceptions and PDF reports. HTTP checks compare linked asset bytes and
JavaScript MIME types. Providers are synthetic; no campaign or spending was run.
The native-link checker, SpecLine plan/spec and hash-bound workflow evidence
have separate receipts. Detailed generated logs stay in `.factory/es-module-audit/`.

Backend Architect, AI Engineer and fresh EGM reviews supplied separate findings
and limits. The EGM review was bounded; it is not full-loop convergence.
Packaged/native installation, physical devices, live provider success and
measured marketing gains are not established by these checks.
