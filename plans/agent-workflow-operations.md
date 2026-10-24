# Plan: agent-workflow-operations
Spec: specs/agent-workflow-operations.md
Architect verdict: PASS

## Architecture
Add four finite operation descriptors: evidence.save, pipeline.prepare, jobs.read and job.cancel. Close nested pipeline input before transport. Share the domain evidence, queue, jobs and cancellation services across the actual loopback HTTP and admitted runtime. Catalog and MCP discovery report implemented grant/review flows accurately while retaining full-domain gaps. Existing grant review policy automatically supports these catalog writes. Never equate an approved enqueue receipt with completed pipeline outputs.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py,tests/test_workflow_operations.py,tests/test_operation_catalog.py | verify=`python -m unittest tests.test_workflow_operations tests.test_operation_catalog -v` | Implement evidence_operations, pipeline_operations, job_observation and job_cancellation with closed input and existing services.
- [x] T2 | slice=mission_control | files=mission_control/server.py,mission_control/agent_operations.py,mission_control/agent_mcp.py,tests/test_agent_operations.py | verify=`python -m unittest tests.test_workflow_operations tests.test_agent_operations tests.test_agent_mcp -v` | Implement current_discovery and exact routes without implicit authority.
- [x] T3 | slice=tests | files=tests/test_workflow_operation_clients.py,tests/test_agent_review_clients.py | verify=`python -m unittest tests.test_workflow_operation_clients tests.test_agent_review_clients -v` | Verify reviewed_workflow and client_conformance through actual CLI and MCP subprocesses, independent synthetic checker identity and real workers.
- [x] T4 | slice=docs | files=docs/agent-workflow-operations.md | verify=`python tools/check_distribution.py` | Explain exact workflow, receipt interpretation, authorization and remaining gaps.

## Acceptance
Run scoped CF architecture/review/QA/drift/smoke, meaningful source mutations, full relevant regression and hash-bound workflow QA. This backend/CLI packet does not change widgets; existing UI uses the dynamic catalog. Preserve unrelated files. No full-product completion or actual provider acceptance follows from this packet alone.
