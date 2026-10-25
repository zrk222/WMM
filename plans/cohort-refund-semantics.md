# Plan: cohort-refund-semantics
Spec: specs/cohort-refund-semantics.md
Architect verdict: PASS (bounded arithmetic-only scope; existing user authorization; local CLI gate does not claim new human identity or provider approval)

This is a bounded derived-arithmetic correction. It reuses the established event-ledger definition of post-refund net proceeds and does not change the data model, source records, or provider boundaries.

- [x] T1 | slice=mission_control | files=mission_control/metrics.py | verify=`python -m unittest tests.test_cohort_refunds -q` | Deduct delivery and acquisition costs from already post-refund net proceeds without subtracting refunds again.
- [x] T2 | slice=tests | files=tests/test_cohort_refunds.py | verify=`python -m unittest tests.test_cohort_refunds -q` | Compare synthetic manual and event-ledger reports for no refund, one partial refund, full refund, zero denominators, and immature follow-up.
- [x] T3 | slice=specs | files=specs/cohort-refund-semantics.md,specs/cohort-refund-semantics.ssat.yaml | verify=`specline strict cohort-refund-semantics --root .` | Validate the scoped requirements and static source/test contract.
- [x] T4 | slice=smoke | files=smoke/cohort-refund-semantics.json | verify=`forge verify-tests cohort-refund-semantics specs/cohort-refund-semantics.ssat.yaml --root .; forge smoke cohort-refund-semantics --root .` | The CLI-operator architecture path in this authorized local scope completed; the AST smoke fails on the empty cohort_metrics stub with NotImplementedError and passes against the real source. This is not a provider approval.
- [x] T5 | slice=.factory/cohort-refund-semantics | files=.factory/cohort-refund-semantics/contract.json,.factory/cohort-refund-semantics/observations.json | verify=`factory audit workflows --root . --contract .factory/cohort-refund-semantics/contract.json --observations .factory/cohort-refund-semantics/observations.json --json` | Candidate and evidence hashes are current; the scoped audit reports PASS without release or deployment authority.
