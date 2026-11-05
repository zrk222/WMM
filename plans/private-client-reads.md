# Plan: private-client-reads
Spec: specs/private-client-reads.md
Architect verdict: PASS

## Architecture
Native SQLite control sessions and immutable per-client Service registry feed a separate finite loopback read HTTP server. Reuse existing services and read-only SQLite mode=ro aggregate SQL; do not call raw workspace/bootstrap. No worker, identity-provider implementation, credential migration, domain mutation or public ingress.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hosted_read_control.py | verify=`python -m unittest tests.test_hosted_read_control` | Add trusted provisioned client memberships, hash-only opaque sessions, epoch invalidation and final authorization receipt transactions.
- [ ] T2 | slice=tests | files=tests/test_hosted_read_control.py | verify=`python -m unittest tests.test_hosted_read_control` | Cover durable sessions, all roles, revoked/reactivated epochs, exact expiry, redaction and receipt failure.
- [ ] T3 | slice=mission_control | files=mission_control/hosted_read_http.py,mission_control/hosted_read_registry.py,mission_control/service.py | verify=`python -m unittest tests.test_hosted_read_http` | Wire actual strict HTTP reads through immutable registered Service handles and whitelisted dashboard projection with final authority recheck.
- [ ] T4 | slice=tests | files=tests/test_hosted_read_http.py | verify=`python -m unittest tests.test_hosted_read_http` | Exercise actual two-store HTTP roles, isolation, forged inputs, concurrency, restart, mid-read revocation and audit failure without providers.

## Remaining full-goal acceptance
Generic sign-in and provisioning UI, HTTPS/public hosted deployment, credential residency, role-aware mutation/worker epoch checks and full hosted dashboard UX remain separate required packets. This increment must be operational through real HTTP before it is counted as functional progress; policy-unit tests alone do not meet its acceptance.
