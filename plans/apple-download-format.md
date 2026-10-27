# Plan: apple-download-format
Spec: specs/apple-download-format.md.
Architect verdict: PASS - offline parser scope only; secure transport and live-provider acceptance remain separate and unapproved.

- [ ] T1 | slice=tests | files=tests/test_apple_analytics_parser.py | verify=`python -m unittest tests.test_apple_analytics_parser -q` | Add documented TSV, categories and malformed-input cases.
- [ ] T2 | slice=mission_control | files=mission_control/apple_analytics_parser.py | verify=`python -m unittest tests.test_apple_analytics_parser -q` | Parse documented TSV and preserve distinct update and restore semantics.
- [ ] T3 | slice=specs | files=specs/apple-download-format.md | verify=`specline strict apple-download-format --root . --json` | Bind scope and unsupported input behavior.
- [ ] T4 | slice=plans | files=plans/apple-download-format.md | verify=`specline tasks apple-download-format --root .` | Preserve independent live transport and provider acceptance boundaries.
