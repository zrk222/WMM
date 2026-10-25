# Plan: agent-gateway-framing
Spec: specs/agent-gateway-framing.md
Architect verdict: PASS

## Architecture
Validate exact singleton framing, then use one five-second bounded reader before
grant admission or reviewed dispatch. Preserve finally-based timeout restoration.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/agent_grant_http.py,mission_control/agent_review_http.py,mission_control/hypit_studio_routes.py,mission_control/http_body.py | verify=`python -m unittest tests.test_agent_gateway_framing -q` | Implement gateway_framing and cumulative gateway_body for human and bearer transports.
- [x] T2 | slice=tests | files=tests/test_agent_gateway_framing.py | verify=`python -m unittest tests.test_agent_gateway_framing -q` | Prove actual loopback rejection and timeout/truncation boundaries without admission.
- [x] T3 | slice=.factory/agent-gateway-framing | files=.factory/agent-gateway-framing/contract.json,.factory/agent-gateway-framing/observations.json | verify=`factory audit workflows --root . --contract .factory/agent-gateway-framing/contract.json --observations .factory/agent-gateway-framing/observations.json --json` | Record focused clients, rejected mutants, independent review and scoped workflow evidence.

## Verification
Seven framing/deadline tests include actual loopback call and all review routes,
truncation, stall and a one-byte-per-second trickle. A separate independent
review runs25 protected HTTP/CLI/MCP/client tests at stable24-file hashes.
Root runs38 focused grant/review/Studio/operation tests and three rejected source
mutants. The existing16MiB bearer and1MiB human limits remain distinct.

The original body fix used an inactivity timeout; independent review reproduced
admission after6.016seconds. Shared read_exact now uses one monotonic deadline,
shrinking socket timeouts and bounded read1; failed connections close, and prior
timeouts restore. Initial boundary-test and original timeout failures are retained.
Broad CF parser/database coverage remains INCOMPLETE; this scoped repair and
manual review do not claim full-goal or provider/release acceptance.
