# Plan: hypit-public-sessions
Spec: specs/hypit-public-sessions.md
Architect verdict: PASS

## Architecture
Use a Service-owned session manager, a durable reservation registry and an
internal fixed project factory. Resolve a current selected-app Hypit source job
from the datastore, validate its frozen inputs with current_inputs, stage an
exclusive private project and construct actual StudioProcess and ParameterBroker
objects. A request-local callback requires protected authority and exact operation
binding before/during native calls. The manager retains actual objects; registry
metadata never restores process authority. Startup summary and native execution
are separate operations. Keep database transactions short around reservations and
results; do not hold writer transactions across installation checks or HTTP.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_studio_registry.py,mission_control/db.py | verify=`python -m unittest tests.test_hypit_studio_registry -v` | Implement session_reservation, session_once, session_restart and session_reconcile with integrity, counted nonterminal capacity across restart and narrow owned-outcome finalization after authority loss.
- [ ] T2 | slice=mission_control | files=mission_control/hypit_studio_factory.py | verify=`python -m unittest tests.test_hypit_studio_factory -v` | Implement session_plan, session_start_scope and session_private using exact app-owned source job/current rights and verified installation; create a new isolated project and private runtime instead of reusing job runtime storage.
- [ ] T3 | slice=mission_control | files=mission_control/hypit_studio_sessions.py,mission_control/service.py | verify=`python -m unittest tests.test_hypit_studio_sessions -v` | Implement session_authority, session_live_authority, session_controls, session_uncertainty, session_cleanup and session_capacity with long-lived actual owned objects, per-session locking and UNKNOWN startup/close outcomes.
- [ ] T4 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py,mission_control/agent_operations.py | verify=`python -m unittest tests.test_hypit_studio_clients -v` | Expose the eight exact shared operations to ordinary/reviewed/standing CLI/MCP server transport and preserve retained uncertain startup/edit/close retry outcomes.
- [ ] T5 | slice=mission_control | files=mission_control/hypit_studio_routes.py,mission_control/server.py | verify=`python -m unittest tests.test_hypit_studio_clients -v` | Expose exact human routes with fresh owner identity, protected binding and strict JSON/session/CSRF boundaries; wire owned service shutdown cleanup.
- [ ] T6 | slice=tests | files=tests/test_hypit_studio_registry.py,tests/test_hypit_studio_factory.py,tests/test_hypit_studio_sessions.py,tests/test_hypit_studio_clients.py | verify=`python -m unittest tests.test_hypit_studio_registry tests.test_hypit_studio_factory tests.test_hypit_studio_sessions tests.test_hypit_studio_clients -v` | Prove concurrent startup reservation, current rights/runtime changes, real clients, cancellation, no resend, restart capacity/reconciliation, revocation plus cleanup/finalizer failure and coordinated shutdown.

## Gates
Fresh CF doctor and scoped SpecLine strict/validator/task gates before code.
Use a reviewed SSAT and Forge architecture/QA, nonhollow behavioral smoke and
guard-removal mutations. Independent Astra review must examine public authority,
startup retry/cleanup ownership, privacy and ambiguity propagation. Run an actual
installed local Hypit end-to-end source-plan/start/edit/read/reject/close probe via
real human and agent clients, verify native cleanup and retain exact source hashes.
Run distribution privacy and hash-bound workflow QA; do not claim product release
from planning, fixture-only tests or an internal callback. Keep full-suite current
acceptance separate from every scoped result and parent editor completion.

## Acceptance evidence
- Exact candidate and installed-runtime hashes with execution identity and timing.
- Actual selected-app summary readback, startup reservation before child creation,
  one native start per startup key and no adopted PID after manager restart.
- Human owner plus ordinary/reviewed/standing agent share exact controls/source
  heads; stale or foreign sessions/fields reject and current cancellation blocks.
- Lost edit reply and retained uncertain retry produce UNKNOWN without another
  native send. Accepted edit/readback and verified rejection remain distinguishable.
- Capacity, failed startup, logout/revocation, server shutdown and response-loss
  cleanup receipts retain unresolved states accurately without leaking paths.
- Typed operation discovery, actual CLI/MCP protocol clients and strict human HTTP
  framing/source/role checks. Complete human UI remains the next parent work.
