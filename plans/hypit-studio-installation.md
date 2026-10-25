# Plan: hypit-studio-installation
Spec: specs/hypit-studio-installation.md
Architect verdict: PASS

## Architecture
One read-only module resolves the installed entrypoint and executing Node, verifies
the reviewed Studio ABI, hashes the contained distribution and revalidates exact
identity. Discovery uses adapter-owned fixed arguments. No caller command, source
execution, account lookup, installation, provider selection or server start occurs.
The future session broker consumes the private fingerprint; public status only
contains aggregate evidence. This increment is a prerequisite, not the broker.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_installation.py | verify=`python -m unittest tests.test_hypit_installation -v` | Implement installation_discovery, reviewed_abi, execution_fingerprint, installation_staleness and evidence_boundary.
- [ ] T2 | slice=tests | files=tests/test_hypit_installation.py | verify=`python -m unittest tests.test_hypit_installation -v` | Prove changed bytes/membership, links, unsupported layouts, malformed manifests, bounds and public privacy with isolated files and fixed discovery spies.

## Gates
CF strict requirement mutants, task validation, focused behavioral tests, actual
installed package fingerprint/readback, rejected source mutations, privacy and
hash-bound workflow QA. A fingerprint pass does not establish Studio startup,
preview execution, runtime cleanup, full control parity or growth outcomes.
