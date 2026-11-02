# Plan: linux-package
Spec: specs/linux-package.md
Architect verdict: PASS

## Architecture
Build a Debian package from the existing frozen runtime and fixed OS launch files. A separately enabled isolated Ubuntu runner checks package identity and native runtime before install, upgrade and removal.

## Tasks
- [ ] T1 | slice=packaging/linux | files=packaging/linux/control,packaging/linux/wize-marketing-machine,packaging/linux/wize-marketing-machine.desktop | verify=`python -m unittest tests.test_linux_package_contract -v` | Define fixed package metadata and launchers.
- [ ] T2 | slice=tools | files=tools/build_linux_package.py,tools/test_linux_package.py | verify=`python -m unittest tests.test_linux_package_contract -v` | Build and verify the package on the isolated Ubuntu runner.
- [ ] T3 | slice=tests | files=tests/test_linux_package_contract.py | verify=`python -m unittest tests.test_linux_package_contract -v` | Check source contracts and fail-closed runner boundaries.

## Gates
Run strict spec and validator gates before code. Local source tests do not establish Ubuntu package acceptance.

- [ ] T4 | slice=.github/workflows | files=.github/workflows/desktop-packages.yml | verify=`python -m unittest tests.test_linux_package_contract tests.test_ci_current_candidate` | Build and exercise native Ubuntu package under an isolated root Secret Service session.
- [ ] T5 | slice=tests | files=tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate` | Preserve intended updated package lifecycle job baseline.

- [ ] T6 | slice=smoke | files=smoke/linux-package.json | verify=`python -m unittest tests.test_linux_package_contract` | Reject archive-format and path-boundary mutations before native installer acceptance.
