# Plan: macos-desktop-preview
Spec: specs/macos-desktop-preview.md
Architect verdict: PASS

## Architecture
Use keyring's explicit macOS Keychain adapter under the existing Vault facade.
Stage the existing frozen engine and hash-bound native window in a standard app
bundle. Native CI artifacts remain separate from signed public distribution.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/macos_vault.py,mission_control/credential_vault.py,tests/test_macos_vault.py,tests/test_linux_vault.py | verify=`python -m unittest tests.test_macos_vault tests.test_linux_vault -v` | Select explicit native storage, scoped addresses, bounded JSON and redacted failures. Preserve rejection of other unsupported platforms.
- [ ] T2 | slice=tools | files=tools/build_desktop.py,tools/build_macos_package.py,tests/test_macos_package.py | verify=`python -m unittest tests.test_macos_package -v` | Reuse the native launcher in an app bundle without operational data or signing claims.
- [ ] T3 | slice=tools | files=tools/check_macos_bundle.py,tools/test_native_desktop_bundle.py,tests/test_desktop_entry.py | verify=`python -m unittest tests.test_macos_package tests.test_native_desktop_package tests.test_desktop_entry -v` | Record packaged lifecycle, native vault cleanup and rejected engine tampering on Mac. Isolate Mac test homes using their Application Support path.
- [ ] T4 | slice=.github | files=.github/workflows/macos-desktop.yml,tests/test_macos_package.py | verify=`python -m unittest tests.test_macos_package -v` | Build declared Mac architectures with pinned native Keychain dependency and retain receipts.
- [ ] T5 | slice=docs | files=docs/macos-desktop-preview.md,docs/requirements-macos.txt | verify=`python -m unittest tests.test_macos_package -v` | Pin native Keychain dependency and explain artifact, architecture, signing and acceptance boundaries.

## Gates
CF strict doctor; strict SpecLine and validator mutation gates; focused Python
tests and native CI; scope-bound security and workflow evidence before merge.
Signed/notarized Mac distribution and first-time user acceptance stay unverified
until their actual receipts exist. No paid account or campaign activation.
