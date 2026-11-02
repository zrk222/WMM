# Host service bounded plan

Reviewed scope: packaging/linux/wmm-worker.service, tools/test_host_service.py, tools/ci_host_user.py, tests/test_host_service_contract.py, and this slice's spec, plan and smoke contract. No runtime, packaging builder, CI workflow or existing user data changes.

1. Declare an opt-in user unit with fixed packaged executable, private umask, SIGTERM shutdown and bounded restart rate.
2. Provide a fail-closed Ubuntu CI harness for an explicitly disposable non-root user manager; use a unique runtime unit link, synthetic workspace, and cleanup only those resources.
3. Provide a separately gated root-only CI wrapper to create, verify and remove a unique disposable account and systemd user manager, then invoke the harness with an explicit minimal environment.
4. Test the contract and preflight rejection locally. The harness must run against the installed package in a suitable isolated Linux CI job to establish lifecycle acceptance.

Gates: strict factory doctor, existing headless assembly route inspection, focused tests and hash-bound workflow evidence. No live providers, service registration on this workstation, deployment or external host acceptance.
