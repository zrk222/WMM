# Plan: windows-installer
Spec: specs/windows-installer.md
Architect verdict: PASS

## Architecture
Inno Setup installs only the already built desktop folder per user. A Windows CI harness compiles, installs, runs isolated executable checks, upgrades and uninstalls while observing a separate synthetic workspace marker.

## Tasks
- [ ] T1 | slice=packaging/windows | files=packaging/windows/WMM.iss | verify=`python -m unittest tests.test_windows_installer_contract -v` | Define the per-user installer and safe launch entries.
- [ ] T2 | slice=tools | files=tools/test_windows_installer.py | verify=`python -m unittest tests.test_windows_installer_contract -v` | Implement isolated Windows installer lifecycle verification.
- [ ] T3 | slice=tests | files=tests/test_windows_installer_contract.py | verify=`python -m unittest tests.test_windows_installer_contract -v` | Validate installer authority and retention boundaries.

## Gates
Run strict spec and validator gates before code. Local contract tests do not establish Windows installation acceptance; execute the lifecycle harness on the isolated Windows runner.

- [ ] T4 | slice=.github/workflows | files=.github/workflows/desktop-packages.yml | verify=`python -m unittest tests.test_windows_installer_contract tests.test_ci_current_candidate` | Compile and execute isolated native install upgrade uninstall on Windows, then retain the distributable remotely.
- [ ] T5 | slice=tests | files=tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate` | Update only the intended desktop job baseline for installer acceptance.

- [ ] T6 | slice=smoke | files=smoke/windows-installer.json | verify=`python -m unittest tests.test_windows_installer_contract` | Verify the source contract rejects missing compiler and unsafe setup defaults before native target acceptance.
