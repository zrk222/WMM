# Plan: studio-request-authority
Spec: specs/studio-request-authority.md
Architect verdict: PASS

## Architecture
Authenticated dispatchers bind a ContextVar containing exact serialized request,
grant identity/version and claimed reviewed checkpoint metadata. A separate
protected context enables database checks at entry and before commit only for
services opting into this execution boundary. Existing domain behavior is not
silently changed. Checks operate on the current database connection and do not
open recursive connections. Standing guards remain authoritative in addition.
Human context freezes fresh verified principal and role version, then checks the
live in-memory identity-session reference locally without network on each chunk.
The upcoming public Studio service must enter protection and bind its callback
to exact action, project and body. No public Studio route is added by this packet.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/operation_authority.py,mission_control/db.py | verify=`python -m unittest tests.test_operation_authority -v` | Implement request_binding, grant_current, review_current, standing_current and commit_current.
- [ ] T2 | slice=mission_control | files=mission_control/operator_identity.py,mission_control/automation_execution.py,mission_control/agent_review_dispatch.py | verify=`python -m unittest tests.test_operation_authority tests.test_agent_review_dispatch tests.test_automation_execution -v` | Bind actual authenticated dispatch and implement human_current without bearer retention.
- [ ] T3 | slice=tests | files=tests/test_operation_authority.py | verify=`python -m unittest tests.test_operation_authority -v` | Prove actual SQLite revocation rollback, exact reviewed claims, standing cancellation, local identity expiry and isolation.

## Gates
CF doctor, strict/validator/task gates, focused actual dispatcher/SQLite tests,
source mutations, independent Astra review, privacy and hash-bound workflow QA.
Parent public broker, session lifecycle and complete human/agent controls remain
required. No provider writes, publishing, spending or deployment is introduced.
