# Reviewed taste agent reads

Extend the existing catalog/gateway only with packaging.taste-read and
packaging.taste-history. Both are private read operations and need current
app-scoped grants, including standing-scope admission where selected. Owner
review/reconciliation remain outside the agent catalog. List at most100 compact
identities; read exact revisions for current evidence status. Empty, offset and
foreign scopes stay explicit. No approval, executor, provider or credentials added.

Owned files: creative_taste_store.py, packaging_access.py, packaging_contract.py,
operation_catalog.py, automation_requirements.py, test_operation_catalog.py and
test_creative_taste_clients.py. Verify owner/CLI/official MCP parity, discovery,
closed inputs, stale status, revocation and inability to approve via agent tool.
Use fresh doctor, scoped CF QA/security, mutations, workflow audit and privacy.
UI authoring and actual production consumption remain required followups.
