# Plan: apple-reconcile-order
Spec: specs/apple-reconcile-order.md.
Architect verdict: PASS - normalize equality of identical source rows only; differently segmented provenance remains an explicit conflict.

- [ ] T1 | slice=tests | files=tests/test_apple_analytics_parser.py | verify=`python -m unittest tests.test_apple_analytics_parser -q` | Cover reordered, duplicate, conflicting and changed-provenance instances.
- [ ] T2 | slice=mission_control | files=mission_control/apple_analytics_parser.py | verify=`python -m unittest tests.test_apple_analytics_parser -q` | Compare multisets of full rows for equal processing dates.
- [ ] T3 | slice=specs | files=specs/apple-reconcile-order.md | verify=`specline strict apple-reconcile-order --root . --json` | Bind parser limits and correction behavior.
- [ ] T4 | slice=plans | files=plans/apple-reconcile-order.md | verify=`specline tasks apple-reconcile-order --root .` | Preserve separate live provider and persistent-partition work.
