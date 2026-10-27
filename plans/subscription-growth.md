# Plan: subscription-growth
Spec: specs/subscription-growth.md (approved under active user goal authorization)
Architect verdict: PASS

Architecture review: extend the app-owned ledger JSON with an explicit versioned
subscription envelope; preserve old bytes and hashes, bind observations to the
existing immutable cohort, and keep provider authority separate. Binary experiment
analysis remains the existing method; monetary significance requires a later
validated method. Separate new modules keep the ledger and UI changes bounded.

## Logical decomposition (phases)
1. UPG-00 freezes requirements, current source hashes, applicability and execution profiles.
2. UPG-01 extends the existing ledger with versioned subscription bindings and reporting.
3. UPG-02 adds typed paywall and offer variants with eligibility and stale-source checks.
4. UPG-03 validates documented store fields and actual experiment surfaces.
5. UPG-04 compares compatible advisory benchmarks without budget authority.
6. UPG-05 links narrow customer workflows and exclusions to source observations.
7. UPG-06 integrates founder review, persistence, recovery and desktop/mobile proof.

## Tasks (atomic — each independently shippable)
<!-- Rules enforced by `specline tasks`: one slice each, <=4 files,
     explicit verify command, no forward references. -->
- [x] T0 | slice=.factory/subscription-growth-closeout | files=.factory/subscription-growth-closeout/requirements-freeze.md,.factory/subscription-growth-closeout/aso-official-source-review.md,.factory/subscription-growth-closeout/category-applicability-review.md | verify=`specline validate subscription-growth && specline strict subscription-growth` | Freeze UPG-00 requirements, source review, execution profiles, preservation boundaries and non-claims.
- [x] T1 | slice=mission_control | files=mission_control/subscription_journey.py,mission_control/ledger.py,tests/test_subscription_journey.py | verify=`python -m unittest tests.test_subscription_journey tests.test_ledger -q` | Add journey_counts, journey_invalid, journey_maturity and journey_history with atomic import and legacy compatibility.
- [x] T2 | slice=mission_control | files=mission_control/subscription_variants.py,mission_control/experiments.py,tests/test_subscription_variants.py | verify=`python -m unittest tests.test_subscription_variants tests.test_experiments -q` | Reject variant_invalid before experiment assessment.
- [x] T3 | slice=mission_control | files=mission_control/aso_validation.py,mission_control/static/growth-review.js,tests/test_aso_validation.py,tests/subscription_authoring.test.cjs | verify=`python -m unittest tests.test_aso_validation -q && node --test tests/subscription_authoring.test.cjs` | Return aso_fields for documented store surfaces, showing Apple's 100-character keyword limit, the conflicting 100-byte reference, both counts and the exact provider-counter check.
- [x] T4 | slice=mission_control | files=mission_control/benchmark_context.py,tests/test_benchmark_context.py | verify=`python -m unittest tests.test_benchmark_context -q` | Return benchmark_scope with compatibility and unknown economics.
- [x] T5 | slice=mission_control | files=mission_control/customer_workflow.py,tests/test_customer_workflow.py | verify=`python -m unittest tests.test_customer_workflow -q` | Bind customer_links and exclusions to research observations.
- [x] T8 | slice=mission_control | files=mission_control/customer_workflow_store.py,mission_control/db.py,tests/test_customer_workflow_store.py | verify=`python -m unittest tests.test_customer_workflow_store -q` | Persist immutable customer workflows beside existing PMF history without rebuilding its constrained table; validate portable records and current source readout.
- [x] T9 | slice=mission_control | files=mission_control/store.py,mission_control/server.py,tests/test_customer_workflow_integration.py | verify=`python -m unittest tests.test_customer_workflow_integration -q` | Wire snapshot export/restore and agent-readable HTTP creation/history with unchanged local authority boundaries.
- [x] T6 | slice=mission_control | files=mission_control/subscription_review.py,mission_control/service.py,tests/test_subscription_review.py,tests/test_subscription_authoring_http.py | verify=`python -m unittest tests.test_subscription_review tests.test_subscription_authoring_http -q` | Integrate review_status with app-owned reporting and recovery.
- [x] T7 | slice=mission_control | files=mission_control/static/growth-review.js,mission_control/static/subscription-authoring.js,tests/subscription_authoring.test.cjs | verify=`node --test tests/subscription_authoring.test.cjs` | Add accessible founder flows and UI contract coverage.
- [x] T10 | slice=tools | files=tools/test_subscription_authoring_browser.py,tools/test_growth_review_ui_browser.py,tools/test_customer_workflow_ui_browser.py | verify=`python tools/test_subscription_authoring_browser.py && python tools/test_growth_review_ui_browser.py && python tools/test_customer_workflow_ui_browser.py` | Verify subscription authoring, ASO listing/review notes, benchmark comparison, and customer evidence at desktop/mobile widths, with keyboard navigation, recovery and export without provider access.
- [x] T11 | slice=.factory/subscription-growth-closeout | files=.factory/subscription-growth-closeout/build_workflow_audit.py,.factory/subscription-growth-closeout/workflow-audit-contract.json,.factory/subscription-growth-closeout/workflow-audit-observations.json,.factory/subscription-growth-closeout/workflow-audit-receipt.json | verify=`python -m factoryline.cli audit workflows --root . --contract .factory/subscription-growth-closeout/workflow-audit-contract.json --observations .factory/subscription-growth-closeout/workflow-audit-observations.json --json` | Bind UPG requirements, current source hashes, runtime profiles, and observed checks to the reviewed scope.

## Verification and authority
Each packet requires CF doctor, scoped ForgeLine and SpecLine proof, regression,
privacy and project-neutral workflow audit. Backend profiles use Python/SQLite;
UI profiles add Node, desktop 1440/mobile 390, keyboard and recovery. Record actual
runtime versions. No provider writes, private activation or release is authorized.
Do not mark the entire feature shipped from a passing individual packet.
