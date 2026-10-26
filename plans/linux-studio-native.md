# Plan: linux-studio-native
Spec: specs/linux-studio-native.md
Architect verdict: PASS

This verdict records the bounded requirements design review in this packet. It
is not a ForgeLine architected-gate receipt or implementation approval.

## Architecture

Preserve `spawn_studio_child(...) -> owner` and `LaunchCleanupPending(owner)` as
the compatibility seam. The Linux implementation is an explicit backend backed
by a unique transient systemd user service, unified cgroup v2 membership, a
fixed trusted supervisor, and a retained owner object. The supervisor is the
unit main process and only starts target argv after it has established private
pipes, exclusive bounded log sinks, a bounded control channel and the target's
captured launcher identity. Target descendants remain in the service cgroup,
including descendants that change session/process group. User/system D-Bus
control sockets and writable cgroup controls must be inaccessible to target
descendants. This is a scoped lifecycle boundary, not a general sandbox against
all same-user compromise.

`StudioChild` behavior must match Windows callers: launcher `poll()` and owner
`stop()` have separate meanings; overflow asynchronously initiates termination;
the exact live loopback listener must belong to the retained unit; cleanup
releases authority only after the manager reports the unit inactive and cgroup
empty; any uncertainty retains retry identity. `studio_command.py` and
`hypit_studio_process.py` should need no new authority model and should keep
their current calls, cleanup receipts and pending-recovery behavior.

## Task packets

- [ ] T1 | slice=mission_control | files=mission_control/studio_child.py,mission_control/studio_child_linux.py | verify=`python -m unittest tests.test_studio_child tests.test_studio_command -v` | Covers studio_launch_authority and studio_native_prerequisites. Define an explicit Linux backend selector and capability probe; implement unique transient service creation with a fixed supervisor executable and no target execution before manager/cgroup authority is confirmed. Reject missing user bus, transient-unit, cgroup-v2, stop/empty-state, sandbox and process-inspection capabilities before launch.
- [ ] T2 | slice=mission_control | files=mission_control/studio_child_linux.py,mission_control/studio_child_supervisor.py | verify=`python -m unittest tests.test_studio_child_linux -v` | Covers studio_owner_contract, studio_dynamic_output_cap and studio_diagnostic_contract. Implement the bounded authenticated supervisor protocol, shell-free target start, independent continuous stdout/stderr drains, shared caller-supplied cap, exclusive log creation, overflow-triggered unit stop, and failure-class-only diagnostics. Keep the supervisor alive until target and descendants finish.
- [ ] T3 | slice=mission_control | files=mission_control/studio_child_linux.py,mission_control/studio_child.py | verify=`python -m unittest tests.test_studio_child_linux tests.test_studio_child tests.test_studio_command -v` | Covers studio_descendant_containment, studio_stop_confirmation, studio_cleanup_retry and studio_escape_confinement. Implement target status observation, stop deadline, exact transient unit stop, inactive plus cgroup-empty confirmation, reader join, idempotence, retained live retry owner after launch/stop errors, and no PID reconstruction. Preserve all existing caller-facing properties/methods and Windows behavior.
- [ ] T4 | slice=mission_control | files=mission_control/studio_child_linux.py,mission_control/studio_listener_linux.py | verify=`python -m unittest tests.test_studio_listener_linux tests.test_studio_child_linux -v` | Covers studio_listener_positive and studio_listener_negative. Implement exact IPv4 loopback TCP LISTEN inspection using NETLINK_INET_DIAG and socket inode mapping; require exact retained cgroup membership, pinned live process identity via pidfd, and second observation before success. Ambiguous, inaccessible, missing or foreign listener remains unowned.
- [ ] T5 | slice=tests | files=tests/test_studio_child_linux.py,tests/test_studio_listener_linux.py,tests/test_studio_command.py,tests/test_hypit_studio_process.py | verify=`python -m unittest tests.test_studio_child_linux tests.test_studio_listener_linux tests.test_studio_command tests.test_hypit_studio_process -v` | Covers studio_deadline_contract in addition to T1–T4 integration. Prove compatibility, positive/boundary/negative lifecycle behavior, launcher-exit descendants including setsid, output overflow without polling, listener replacement/foreign ownership, unsupported capability fail-closed behavior, manager loss, retry identity, and unrelated-process preservation. Mocks may validate protocol branching only and cannot satisfy native acceptance.
- [ ] T6 | slice=tests | files=tests/linux/test_studio_native_acceptance.py | verify=`python -m unittest tests.linux.test_studio_native_acceptance -v` | Covers all 12 requirement IDs on the real native host, especially studio_native_prerequisites, studio_cleanup_retry, studio_escape_confinement and studio_listener_positive/negative. Run the acceptance matrix on real Ubuntu desktop hosts with user systemd and unified cgroup v2, recording release/kernel/systemd/cgroup/pidfd/INET_DIAG and manager-socket isolation evidence. Test Focal 20.04, Jammy 22.04 and Noble 24.04 separately or list exact missing hosts as NOT_RUN; never treat Docker or this Windows checkout as native evidence.

## Order and gates

T1 defines the prerequisite and pre-execution contract. T2 establishes the
trusted service and supervisor protocol. T3 seals stop and recovery semantics.
T4 provides listener identity. T5 covers deterministic tests. T6 is independent
host acceptance after implementation and remains blocked until matching native
Ubuntu hosts are available. Do not release or claim Linux support until all
required tests pass and native host evidence exists for each declared supported
Ubuntu profile. Until native cleanup, manager-socket/cgroup escape, listener,
and unit-isolation proofs pass, do not implement from this packet, enable the
Linux backend, or claim Linux support. Unsupported host capability remains a
fail-closed result.

## Evidence and constraints

- Requirements source review: `studio_child.py`, `studio_command.py`,
  `hypit_studio_process.py`, `test_studio_child.py`, and
  `test_studio_command.py` at reviewed baseline commit `41e337e` in the frozen
  Windows checkout. This plan applies no edits to that checkout.
- Native Linux desktop/systemd/cgroup/pidfd/NETLINK_INET_DIAG acceptance:
  `NOT_RUN`. This Windows host/container environment is not evidence for those
  claims. No implementation or full Linux support is claimed by this packet.
- User manager version differences shall be handled by capability probing.
  Ubuntu package baselines observed during research were systemd 245.x on
  Focal, 249.11 on Jammy and 255.4 on Noble; installed versions can differ.
- Kernel cgroup v2 documents fork inheritance and delegated-subtree boundaries:
  <https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html>.
  systemd service kill behavior is specified at
  <https://www.freedesktop.org/software/systemd/man/253/systemd.kill.html>.
  systemd-run distinguishes service from caller-launched scope at
  <https://freedesktop.org/software/systemd/man/latest/systemd-run.html>.
  Kernel `/proc` documents socket inode links and PID-FD reuse limits at
  <https://www.kernel.org/doc/html/latest/filesystems/proc.html>.
