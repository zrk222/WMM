# Plan: ci-agent-profile
Spec: specs/ci-agent-profile.md
Architect verdict: PASS

- [x] T1 | slice=.github/workflows | files=.github/workflows/checks.yml | verify=`python -m unittest tests.test_agent_cli tests.test_agent_mcp -q` | Add ci_mcp_profile and ci_browser_profile using declared dependencies and existing test files.
- [x] T2 | slice=.factory/ci-agent-profile | files=.factory/ci-agent-profile/contract.json,.factory/ci-agent-profile/observations.json | verify=`factory audit workflows --root . --contract .factory/ci-agent-profile/contract.json --observations .factory/ci-agent-profile/observations.json --json` | Bind config, declared requirements, local equivalent commands and separate remote verification.

Local equivalent commands pass: MCP1.30 prerequisite;106Node browser logic tests;16PythonCLI/MCP/setup tests. YAML parse and declareddependency/command selection checks pass. Hosted run remains separate and pending; local evidence is not a green GitHub receipt.
