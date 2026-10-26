# Plan: linux-provider-signing
Spec: specs/linux-provider-signing.md
Architect verdict: PASS
Reviewed scope: in-process P-256 parsing/signing and existing protected connection contracts; no external provider execution.

- [ ] T1 | slice=mission_control | files=mission_control/provider_crypto.py,mission_control/provider_auth.py | verify=`python -m unittest tests.test_provider_crypto -v` | Implement bounded optional Linux crypto operations with existing Windows dispatch preserved.
- [ ] T2 | slice=tests | files=tests/test_provider_crypto.py,tests/test_provider_setup.py | verify=`python -m unittest tests.test_provider_crypto tests.test_provider_setup tests.test_http -v` | Prove actual signatures, platform-neutral fixture generation, protected key rotation and HTTP workflow scope.
- [ ] T3 | slice=docs | files=docs/linux-protected-credentials.md | verify=`python tools/check_distribution.py` | Document explicit Linux package setup and evidence limits.
