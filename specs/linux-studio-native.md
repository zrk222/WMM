# Spec: linux-studio-native
Status: requirements

## Scope

Add a native Linux implementation of the existing owned Studio child lifecycle.
This packet freezes requirements and implementation slices; it does not claim
implementation or Linux acceptance. The normal supported path runs on the local
Linux desktop and requires no Windows, WSL, Docker, or remote WMM host.

## MUST - Functional core

### Requirements (EARS)

- The system shall return launch-ready only after the local systemd user manager confirms a unique transient service and its cgroup authority, then start the requested Studio target, identified by `studio_launch_authority`.
- When local manager, transient-service, unified-cgroup-v2, pidfd, NETLINK_INET_DIAG or containment capability probes fail, the system shall return a stable unsupported-capability error before executing a helper or requested target; the backend shall require no root or administrator privilege, identified by `studio_native_prerequisites`.
- The system shall preserve the existing caller owner contract: diagnostic launcher PID, launcher exit status, overflow and capture-failure flags, exact listener-ownership observation, and stop on the same retained owner object, identified by `studio_owner_contract`.
- While the target launcher has exited and its cgroup remains populated, the system shall retain live stop authority; on stop, the system shall report a stopped-tree result only after all attempt descendants exit, including a descendant that calls `setsid`, identified by `studio_descendant_containment`.
- When combined stdout and stderr bytes exceed the caller-supplied `max_log_bytes`, the system shall retain no more than `max_log_bytes` bytes and request owned-unit termination without caller polling, identified by `studio_dynamic_output_cap`.
- When stop begins, the system shall stop only the exact attempt unit and release live authority only after unit inactivity, cgroup populated state equal to 0, and output-drain completion are confirmed within 10 seconds, identified by `studio_stop_confirmation`.
- If launch rollback or stop cannot confirm an empty cgroup, the system shall store the live owner object and emit cleanup-unconfirmed state; a subsequent stop call on that same object shall attempt cleanup again, identified by `studio_cleanup_retry`.
- The system shall return listener-owned only when two consecutive observations confirm the exact IPv4 `127.0.0.1` endpoint and port, socket inode, live pidfd-bound task identity and membership in the exact attempt cgroup, identified by `studio_listener_positive`.
- When listener ownership is absent, ambiguous, inaccessible, stale or foreign, the system shall return listener-unowned or emit inspection failure and reject adoption or termination of a foreign listener owner, identified by `studio_listener_negative`.
- The system shall return native-host-unsupported and reject target execution unless user and system service-manager control sockets and writable cgroup control files are inaccessible to the target and descendants, identified by `studio_escape_confinement`.
- The system shall return startup-timeout after 45 seconds, HTTP-timeout after 2 seconds, command-timeout at the caller-provided 1–180 second deadline (120 seconds by default), and unconfirmed-stop after 10 seconds, identified by `studio_deadline_contract`.
- The system shall create exclusive-new private log files, retain output only up to the caller-supplied byte cap, emit UTF-8 replacement snapshots, and store only closed failure codes or exception classes in failure records, identified by `studio_diagnostic_contract`.

## Acceptance criteria

```gherkin
Scenario: studio_launch_authority
  Given a local user manager and a target launch request
  When `studio_launch_authority` confirms unique transient-unit cgroup authority
  Then the requested target starts only after that confirmation

Scenario: studio_native_prerequisites
  Given any required local capability is missing or root privilege would be required
  When `studio_native_prerequisites` checks the host before launch
  Then the system returns unsupported-capability and executes no helper or target

Scenario: studio_owner_contract
  Given a live owner returned to existing Studio callers
  When `studio_owner_contract` observes exit, overflow, capture failure, listener ownership and stop
  Then each observation comes from the same live owner and a PID value grants no stop authority

Scenario: studio_descendant_containment
  Given a target forks a descendant that calls `setsid` and outlives its launcher
  When `studio_descendant_containment` stops the attempt
  Then the descendant exits or stop remains unconfirmed with live authority retained

Scenario: studio_dynamic_output_cap
  Given `max_log_bytes` and descendants writing to stdout and stderr
  When `studio_dynamic_output_cap` observes combined bytes exceed the supplied cap
  Then no more than the supplied cap is retained and owned-unit termination starts without caller polling

Scenario: studio_stop_confirmation
  Given a running transient unit with captured output
  When `studio_stop_confirmation` requests stop
  Then the owner releases authority only after unit inactivity, cgroup populated state equal to 0 and drain completion within 10 seconds

Scenario: studio_cleanup_retry
  Given a launch rollback or stop that cannot confirm an empty cgroup
  When `studio_cleanup_retry` invokes stop again on the retained live owner
  Then cleanup is retried and no persisted PID or unit name reconstructs authority

Scenario: studio_listener_positive
  Given an owned descendant listening on IPv4 loopback
  When `studio_listener_positive` checks endpoint, inode, live identity and attempt membership twice
  Then the exact `127.0.0.1` listener is accepted after launcher exit

Scenario: studio_listener_negative
  Given a foreign, ambiguous, stale, missing or inaccessible loopback listener
  When `studio_listener_negative` inspects its owner
  Then the listener is rejected or inspection failure is emitted without signaling a foreign owner

Scenario: studio_escape_confinement
  Given the target attempts user or system manager access or cgroup migration
  When `studio_escape_confinement` checks launch confinement
  Then the target is not executed unless manager sockets and writable cgroup files are inaccessible

Scenario: studio_deadline_contract
  Given Studio startup, HTTP observation, command capture and unit-stop operations
  When `studio_deadline_contract` applies caller deadlines
  Then the respective bounds are 45 seconds, 2 seconds, 1–180 seconds with 120 seconds default, and 10 seconds

Scenario: studio_diagnostic_contract
  Given target output and diagnostic failures
  When `studio_diagnostic_contract` writes and snapshots logs
  Then files are exclusive-new and private, bytes obey `max_log_bytes`, text uses replacement decoding, and failures expose closed codes only

```

## SHOULD - Technical constraints

Keep the existing
`spawn_studio_child(argv, folder, env, stdout_path, stderr_path, max_log_bytes)`
interface and owner attributes/methods: `pid` is diagnostic only; `poll()`,
`overflow`, `failure`, `owns_listener(port)`, and `stop()` preserve their current
meanings. Preserve `LaunchCleanupPending(owner)` and generic process-capture
semantics.

Use a unique transient systemd user service and a fixed trusted supervisor as
the service main process. The supervisor starts target argv without a shell
only after service/cgroup authority is established. It remains until target
descendants end; a bounded authenticated channel controls observation and stop.
Use `KillMode=control-group`, final SIGKILL after bounded graceful stop,
`ProtectControlGroups=yes`, `NoNewPrivileges=yes`, no delegated writable cgroup
subtree, and inaccessible user/system manager sockets. Probe each requirement at
runtime instead of relying on distribution labels. Do not use `systemd-run
--scope`: systemd documents that scope commands are launched by systemd-run
itself and run synchronously.

Use unified cgroup v2 membership and `cgroup.events populated=0` as the empty
tree observation. Children inherit the cgroup; descendant session changes do
not move them. Transient service membership is not by itself an isolation
guarantee: the user bus may let a same-user child create sibling units, and a
writable cgroup path may let it migrate. The acceptance test must attempt both
paths and inspect all manager sockets visible to the target. If same-user
manager sockets cannot be hidden while preserving the filesystem access required by Studio
and loopback behavior, the backend is unsupported until a stronger local design
is available.

Use NETLINK_INET_DIAG for listener state and map socket inode through
`/proc/{pid}/fd`; read `/proc/{pid}/cgroup`, pin a live identity with pidfd, then
repeat address, port, inode, membership and liveness checks. Do not use
`/proc/net/tcp` as the preferred backend; kernel documentation marks it
deprecated in favor of tcp_diag. If pidfd or required inspection access is
unavailable, fail closed rather than falling back to PID-only identity.

Acceptance requires a real Ubuntu desktop host with a local user systemd manager
and bus, unified cgroup v2, service control and process/socket inspection. Record
Ubuntu release, kernel, systemd version, cgroup mode, user manager, D-Bus socket
denial, pidfd and NETLINK_INET_DIAG results. Test Ubuntu 20.04/Focal,
22.04/Jammy and 24.04/Noble separately; feature probes determine support. The
researched package baselines were systemd 245.x, 249.11 and 255.4 respectively;
installed updates may differ. Native host acceptance is `NOT_RUN`. Windows
tests, mocks, static validators, source review and Docker do not satisfy it.

Official references: [kernel cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html),
[systemd kill behavior](https://www.freedesktop.org/software/systemd/man/253/systemd.kill.html),
[systemd-run](https://freedesktop.org/software/systemd/man/latest/systemd-run.html),
[kernel procfs](https://www.kernel.org/doc/html/latest/filesystems/proc.html),
[Ubuntu Focal systemd-run](https://manpages.ubuntu.com/manpages/focal/man1/systemd-run.1.html),
[Ubuntu Jammy systemd-run](https://manpages.ubuntu.com/manpages/jammy/man1/systemd-run.1.html),
[Ubuntu Noble systemd-run](https://manpages.ubuntu.com/manpages/noble/man1/systemd-run.1.html).

## Non-goals

This work does not provide a general hostile-code sandbox, rootless container
runtime, cgroup delegation service, remote runner or arbitrary process
supervisor. It does not change Studio admission, grants, project validation,
HTTP behavior, installation identity, source mutation policy or the Windows
backend. This packet does not claim Linux implementation, full platform support,
release readiness or successful native acceptance.
