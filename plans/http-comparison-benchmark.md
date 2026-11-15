# Plan: http-comparison-benchmark
Spec: specs/http-comparison-benchmark.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=tools | files=tools/benchmark_http.py | verify=`python -m unittest tests.test_http_benchmark -q` | Measure isolated baseline and bounded-pool adapters with route/auth/CSRF parity and process memory.
- [ ] T2 | slice=tests | files=tests/test_http_benchmark.py | verify=`python -m unittest tests.test_http_benchmark -q` | Reject mismatched parity and malformed samples; exercise both real local servers.
- [ ] T3 | slice=docs | files=docs/HTTP-BENCHMARK.md,docs/evidence/http-benchmark-2026-11-12.json | verify=`python tools/benchmark_http.py` | Record actual p50/p95/RSS and exact comparison limits.
- [ ] T4 | slice=tools | files=tools/maintained_files.txt | verify=`python tools/check_types.py` | Enroll benchmark and test sources.
