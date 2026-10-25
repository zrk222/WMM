# Plan: hypit-session-manager
Spec: specs/hypit-session-manager.md
Architect verdict: PASS

## Architecture
Manager dispatch accepts a frozen envelope from authenticated request context and
enters protected(). Its context-local active call binds manager/app/session/action/
body. A common callback checks exact active request, protected DB authority and
current frozen source/rights. Each actual session has a separate lock and owned
broker; the manager lock only coordinates admission and object maps. Registry
reserves capacity before source preparation or child creation. Ambiguity uses the
existing typed EffectUncertain and never infers safe retry from retained metadata.
Owned outcome finalization is narrowly isolated from revoked request contexts,
while native cleanup uses actual held process objects only. Shutdown blocks new
admission, waits for active calls and then closes owned objects without adopting
native authority from saved metadata. Standalone manager is internal until shared
server/HTTP/CLI/MCP wiring and restart inspector are completed.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_studio_sessions.py | verify=`python -m unittest tests.test_hypit_studio_sessions -v` | Implement manager_authority, manager_once, manager_live, manager_unknown, manager_finalization, manager_restart, manager_serialization and manager_shutdown.
- [ ] T2 | slice=tests | files=tests/test_hypit_studio_sessions.py | verify=`python -m unittest tests.test_hypit_studio_sessions -v` | Prove actual protected request/SQLite dispatch, controlled owned broker calls, concurrent retries and cleanup after revocation/storage failure.

## Gates
CF strict/validator/task checks, meaningful behavioral guard mutations, scoped
Forge architecture/nonhollow/smoke, Astra review, actual installed local manager
probe, privacy and hash-bound workflow QA. No public integration or complete editor
claim from this internal manager. Keep all parent tasks and scope mandatory.
