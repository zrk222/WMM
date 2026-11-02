# Plan: desktop-entry
Spec: specs/desktop-entry.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/desktop.py,mission_control/server.py | verify=`python -m unittest tests.test_desktop_entry` | Reuse existing server with user-private data, actual loopback port and visible close control.
- [ ] T2 | slice=tests | files=tests/test_desktop_entry.py | verify=`python -m unittest tests.test_desktop_entry` | Verify private paths, occupied-port recovery, clean shutdown and adapter dispatch.

## Next packaging gate
Remote native runtime bundle, clean-machine browser smoke, terminal-free installation, retained user data on upgrade and agent CLI/MCP transport smoke are required before claiming packaged delivery.

- [ ] T3 | slice=tools | files=tools/build_desktop.py,tools/smoke_desktop_bundle.py | verify=`python -m unittest tests.test_desktop_entry` | Build explicit clean folder bundle and verify actual executable bootstrap/static/CLI paths.
- [ ] T4 | slice=.github/workflows | files=.github/workflows/desktop-packages.yml | verify=`python tools/build_desktop.py --plan` | Build Windows/Ubuntu bundles on matching clean CI and retain small release artifacts only remotely.

- [ ] T5 | slice=mission_control | files=mission_control/desktop.py | verify=`python -m unittest tests.test_desktop_entry` | Add an explicit synthetic native credential roundtrip with verified cleanup and no secret output.
- [ ] T6 | slice=tools | files=tools/build_desktop.py,tools/smoke_desktop_bundle.py | verify=`python -m unittest tests.test_desktop_entry` | Bundle Linux SecretStorage and run real native vault acceptance in isolated clean CI.

- [ ] T7 | slice=.github/workflows | files=.github/workflows/desktop-packages.yml | verify=`python -m unittest tests.test_desktop_entry` | Provision disposable Linux Secret Service and run native frozen vault checks.
- [ ] T8 | slice=tests | files=tests/test_desktop_entry.py | verify=`python -m unittest tests.test_desktop_entry` | Verify synthetic vault cleanup and no secret output on success and failure.
