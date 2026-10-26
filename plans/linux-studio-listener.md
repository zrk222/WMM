# Plan: linux-studio-listener
Spec: specs/linux-studio-listener.md
Architect verdict: PASS
Status: parent architecture review accepted fd/callback, bounds and member-witness semantics for component development; no implementation acceptance.

- [ ] T1 | slice=mission_control | files=mission_control/studio_listener_linux.py | verify=`python -m unittest tests.test_studio_listener_linux -v` | Implement listener_exact_identity, listener_live_scope, listener_fail_closed and listener_bounded_resources using retained descriptor authority, kernel diagnostics, bounded retained-member proc mapping, pidfd liveness and repeated observations. No activation or signalling.
- [ ] T2 | slice=tests | files=tests/test_studio_listener_linux.py | verify=`python -m unittest tests.test_studio_listener_linux tests.test_studio_child tests.test_studio_command tests.test_hypit_studio_process -v` | Prove parser/budget/ownership/error cleanup branches with fixtures and preserve the existing Windows caller seam. Kill meaningful source mutants. Mocks prove branching only.
- [ ] T3 | slice=specs | files=specs/linux-studio-listener.ssat.yaml | verify=`forge qa linux-studio-listener --ssat specs/linux-studio-listener.ssat.yaml --root . --strict` | Freeze scoped interface/function inventory and enforce source complexity at most 10; run strict validator/challenge and candidate-bound workflow audit without full-host prerequisite circularity.

Parent review approved the exact interface, resource/deadline limits and distinction
between future service-owner authority and component descriptor validation. It
required retained-member scans, acceptance of same-scope inherited holders and a
stable witness instead of global scans or exclusive ownership. The rejected design
is retained in ignored evidence. Commit only after parent reviews implementation evidence;
the commit remains local WIP/unaccepted. No global tool changes or installs.

Run real component-only checks using a separate read-only checkout mount in the
existing offline `wmm-ubuntu-workflows:local` image. Record image/kernel/Python
identities and actual netlink/pidfd/cgroup results. No mount or container privilege
change may be used to simulate systemd isolation. Native desktop/service-manager
T1-T3/T6 activation/admission remain NOT_RUN; component development does not require
their completion. No full-support claim follows from Docker or Windows tests.
