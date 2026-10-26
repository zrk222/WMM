# Spec: linux-studio-listener
Status: PARENT-REVIEWED COMPONENT ARCHITECTURE / IMPLEMENTATION UNACCEPTED
Parent: linux-studio-native T4 at 176ee1a. No backend activation or process signalling.

## MUST - Functional core
### Requirements (EARS)
- The system shall return listener-owned only after 2 observations agree on exact IPv4 127.0.0.1 TCP LISTEN port, inode, socket cookie, pidfd-live task identity and retained cgroup membership, identified by `listener_exact_identity`.
- The system shall require an internal retained cgroup directory descriptor with verified cgroup-v2 filesystem identity and a live-owner callback before reading membership, reject persisted PID unit or path strings as authority, and release duplicated descriptors on close, identified by `listener_live_scope`.
- The system shall reject missing ambiguous wildcard IPv6 foreign stale inaccessible malformed or truncated listener evidence without falling back to shell ps ss or PID-only identity and without signalling any task, identified by `listener_fail_closed`.
- The system shall bound each inspection to at most 2 seconds, 1048576 diagnostic bytes, 8192 netlink messages, 4096 task directories per observation, 4096 descriptors per task, 32768 total descriptor links per observation and 65536 bytes per proc or cgroup file read, identified by `listener_bounded_resources`.
- The system shall return component measurements with 0 service-manager calls distinct from native systemd containment and full platform acceptance, retaining activation and native desktop gates as NOT_RUN, identified by `listener_evidence_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: listener_exact_identity
  Given a live retained scope and a listener at the selected IPv4 loopback port
  When `listener_exact_identity` observes the kernel socket and live scoped task twice
  Then identical address port inode cookie and task identity produce true
  And replacement death or migration between observations prevents true
Scenario: listener_live_scope
  Given a retained cgroup descriptor and its current owner callback
  When `listener_live_scope` encounters revoked ownership a closed descriptor or another filesystem
  Then membership is rejected and all inspection descriptors are closed
  And a persisted PID unit or path cannot reconstruct scope authority
Scenario: listener_fail_closed
  Given missing ambiguous foreign wildcard IPv6 malformed or inaccessible evidence
  When `listener_fail_closed` inspects the proposed listener
  Then ownership is false or an inspection failure is emitted
  And no fallback command or process signal occurs
Scenario: listener_bounded_resources
  Given the declared 2 seconds and inventory and byte bounds
  When `listener_bounded_resources` reaches any bound or receives a truncated netlink dump
  Then inspection fails without accepting a partial inventory or leaking descriptors
Scenario: listener_evidence_boundary
  Given unit branching tests and an Ubuntu container kernel component experiment
  When `listener_evidence_boundary` reports their results
  Then the report identifies those exact component scopes
  And native user-systemd containment activation and desktop support remain NOT_RUN
```

## Frozen proposed interface and algorithm

`RetainedCgroup(directory_fd, owner_alive)` duplicates a caller-retained directory
descriptor, records its device/inode and verifies cgroup2 filesystem magic. The
callback is a trusted internal capability seam from the future service owner;
it must return exactly True only while the original attempt authority is live.
This object cannot establish transient-unit authority itself. It accepts no path,
PID or unit-name authority and is not exposed as a user operation. `members(deadline)`
revalidates callback, descriptor identity, cgroup domain type and bounded
`cgroup.procs` through openat/O_NOFOLLOW; `close()` is idempotent. The caller owns
its original descriptor; this component owns only its duplicate.

`owns_listener(scope, port, timeout=1.0) -> bool` accepts only that live capability,
an integer port 1-65535 and finite timeout 0-2 seconds (strictly positive). It opens
a NETLINK_INET_DIAG/SOCK_DIAG IPv4 TCP LISTEN dump with a per-request sequence;
validates kernel sender, framing/flags/sequence, DONE/error, aligned attributes,
dump completeness and budgets. Only a unique exact 127.0.0.1 candidate is eligible;
wildcard or IPv6 sockets never count as the selected endpoint.

Map that inode through only the bounded live retained cgroup.procs member/fd inventory.
Open a pidfd before reading a task directory, inspect link identities and bounded
`/proc/PID/cgroup`, and require the task in the descriptor-backed cgroup.procs
membership. A live pidfd pins the selected task throughout both observations.
Require a live retained member holding the unique diagnostic inode and cookie.
Multiple same-scope members sharing an inherited socket are permitted; select
and recheck a stable live witness rather than requiring exclusive ownership.
Repeat the diagnostic dump and process/fd/membership/cgroup read, compare socket
cookie/inode and task identity, and recheck both pinned task and scope liveness.
No adopted listener is ever signalled by this module.

Inspection failure raises Invalid with a closed public code; absent/foreign/dead
or changed evidence returns False. Permission/inventory uncertainty raises Invalid.
An inaccessible required retained-member task/fd/cgroup read fails closed.
Unrelated tasks are never enumerated, so unrelated permission restrictions cannot
disable a valid owned witness. Witness death, migration, replacement or missing
membership prevents success. This proves only that a current retained member
holds the exact listener; it does not prove exclusivity against other same-user
or root adversaries, nor reserve a future TCP connection atomically. Future unit
containment and existing HTTP protocol/source checks remain required.

All directory/link enumerations, proc/cgroup reads and netlink receives check the
same monotonic deadline. Reads use bounded nonblocking descriptors. Linux kernel
procfs/cgroup operations are expected bounded syscalls, not an enforceable kernel
preemption guarantee; a stalled kernel syscall remains outside this user-space
deadline claim. The live-owner callback is trusted and likewise non-preemptible.
Once control resumes, post-validation and final-success deadline checks prevent
returning True after elapsed time exceeds the deadline. No callback or kernel
preemption is promised. No subprocess, external command, shell, ps, ss, signal or service
manager call is performed. Missing Linux/pidfd/netlink primitives fail closed.

## Scope and evidence boundaries

Own only mission_control/studio_listener_linux.py, its test module, this spec/plan,
scoped SSAT and ignored CF evidence. Do not change `studio_child.py`, choose a
Linux backend, launch Studio or activate a unit. Existing owner.owns_listener(port)
will call this component only after future T1-T3 service-owner integration.

The earlier global scan/exclusive-holder proposal was rejected by parent review
because it exceeded the existing Windows owner semantics and denied ordinary
unprivileged desktop use. Its text is retained in ignored review evidence.
Mock tests establish parsing and failure branching only. Docker checks may show
actual kernel netlink, procfs, pidfd and read-only retained-cgroup behavior in the
existing offline Ubuntu image. A container-root cgroup is not an isolated WMM
attempt service and cannot prove user-systemd ownership, manager-socket hiding,
cgroup escape prevention or desktop support. T1-T3 and T6 remain required.

Protocol basis: [Linux sock_diag](https://man7.org/linux/man-pages/man7/sock_diag.7.html),
[netlink framing](https://man7.org/linux/man-pages/man7/netlink.7.html), and
[kernel cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html).
These references establish interfaces, not observed WMM behavior.
