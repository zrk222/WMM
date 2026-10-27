# Plan: apple-analytics-parser
Spec: specs/apple-analytics-parser.md. Parent: plans/apple-analytics-metrics.md.
Architect verdict: PASS - bounded offline parsing; independent review and provider validation remain outstanding.

- [x] T1 | slice=tests | files=tests/test_apple_analytics_parser.py | verify=`python -m py_compile tests/test_apple_analytics_parser.py` | Define synthetic complete, malformed, foreign and correction cases before parser implementation.
- [x] T2 | slice=mission_control | files=mission_control/apple_analytics_parser.py | verify=`python -m unittest tests.test_apple_analytics_parser -v` | Parse complete named-column report instances and reconcile latest complete date without network or persistent effects.
- [x] T3 | slice=specs | files=specs/apple-analytics-parser.md | verify=`specline strict apple-analytics-parser --root . --json` | Bind six requirements and distinguish offline tests from provider acceptance.
- [x] T4 | slice=plans | files=plans/apple-analytics-parser.md | verify=`specline tasks apple-analytics-parser --root .` | Preserve atomic scope and parent completion boundaries.

An explicit caller attestation of complete segment enumeration is necessary; it
is not evidence of provider completeness until the future scoped transport
verifies pagination. No simulated input establishes real app data or an outcome.
