# Plan: hypit-installation-path-normalization
Spec: specs/hypit-installation-path-normalization.md

Architect verdict: PASS - test-only change compares canonical paths and leaves discovery runtime unchanged.

- [x] T1 | slice=tests | files=tests/test_hypit_installation.py | verify=`python -m unittest tests.test_hypit_installation -q` | Compare resolved npm paths, conditionally exercise a native 8.3 alias and assert capture is not called for direct or npm discovery.
- [x] T2 | slice=specs | files=specs/hypit-installation-path-normalization.md | verify=`specline strict hypit-installation-path-normalization --root .` | Record the test-only scope and canonical path acceptance.
- [x] T3 | slice=.factory/hypit-path-normalization | files=.factory/hypit-path-normalization/contract.json,.factory/hypit-path-normalization/observations.json | verify=`factory audit workflows --root . --contract .factory/hypit-path-normalization/contract.json --observations .factory/hypit-path-normalization/observations.json --json` | Bind focused tests, privacy check, unchanged source and CI failure context to current hashes.

The CI failure reported from run 40175601617 was one assertion mismatch: the
test compared a short expected `RUNNER~1` path to `Path.resolve()`'s long path.
Its report also showed 1,383 tests with 18 skips from the optional MCP dependency.
Those are parent-supplied GitHub observations, not a rerun in this packet.
