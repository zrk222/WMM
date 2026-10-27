# Checklist transport packet

Ownership: packaging_access.py, operation_catalog.py, automation_requirements.py,
packaging_contract.py, tests/test_packaging_handoff_clients.py and the catalog
count regression only. Requirement T5 R2/R6: expose packaging.checklist as a
read-only private-data operation with exactly manifest_version and shots input.
Reuse existing owner/grant HTTP/CLI/official MCP dispatch, bound-owner checks,
protected transactions and read-only checklist. No executor or approval is added.
Tests must compare all three transports and reject stale revisions, wrong scope,
revoked grants and injected approval fields, while proving zero jobs created.
Candidate security scope reuses the twenty exact source set; QA isolates changed
catalog declarations/functions rather than altering unrelated catalog validation.
