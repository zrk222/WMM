# Plan: platform-parity
Spec: specs/platform-parity.md
Architect verdict: PASS
Scope: requirements and atomic task review only; implementation and native/device proof remain NOT_RUN.

- [ ] T1 | slice=mission_control | files=mission_control/credential_vault.py,mission_control/platform_capabilities.py | verify=`python -m unittest tests.test_platform_vault -v` | Implement explicit native protected backend selection and capability readback without plaintext fallback; prove locked-service recovery on Linux and Ubuntu.
- [ ] T2 | slice=mission_control | files=mission_control/agent_native.py,mission_control/native_runtime_identity.py | verify=`python -m unittest tests.test_agent_native -v` | Remove verified platform assumptions and prove installed agent discovery invocation cancellation and current authority on declared Linux profiles.
- [ ] T3 | slice=tests | files=tests/test_platform_workflows.py | verify=`python -m unittest tests.test_platform_workflows -v` | Execute complete provider media approval telemetry analytics and export acceptance on Linux and Ubuntu with isolated synthetic provider data and real native media tools.
- [ ] T4 | slice=specs | files=specs/ios-client.md | verify=`specline strict ios-client --root .` | Freeze a standalone native iOS app with Keychain, local durable SQLite jobs, native media processing and authenticated authority; reject any required paired or remote WMM worker.
- [ ] T5 | slice=tests | files=tests/ios_acceptance.md | verify=`python tools/check_platform_receipts.py --profile ios` | Record actual iOS workflow keyboard/touch file-picker preview editing approval continuity PDF and accessibility evidence; simulations cannot substitute for device gates.
- [ ] T6 | slice=tools | files=tools/check_platform_receipts.py | verify=`python tools/check_platform_receipts.py --all` | Bind each declared platform to exact source runtime and workflow receipts, preserving Windows regressions and missing device/native states.

- [ ] T7 | slice=.github | files=.github/workflows/platform-checks.yml | verify=`python tools/check_platform_receipts.py --ci-contract` | Run declared native platform profiles in CI and retain native and device acceptance gaps without promoting synthetic tests to full platform support.

Standalone acceptance overrides any earlier paired-host architecture. iOS must include an installable native target and actual-device acceptance; Linux/Ubuntu must run locally without Windows/WSL. Preserve all workflow requirements and mark unavailable evidence NOT_RUN.
