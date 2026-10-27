# R2 checklist implementation packet

Requirement: content-packaging-t5 R2. Ownership: new
mission_control/packaging_handoff.py and tests/test_packaging_handoff.py only.
Architecture: read-only native SQLite snapshot; reuse Packaging latest/readback,
app_context, exact reference contract and derivative_snapshot. No new storage,
authority, executor or transport. Exact current document revision/hash and app
manifest are mandatory. Report stale upstream evidence separately from forged
document identity. Every shot keeps its script hash, research source and selected
media identities. Still assets cannot masquerade as timed video. Frame mapping,
audio/taste review and execution remain later required decisions.

Verify real temporary SQLite, stale app/source/claim and foreign/revised documents,
still-only rows, actual reviewed media and no-write repeatability. Run focused
regressions, source mutants, scoped function QA and complete declared Python
security coverage, privacy and a project-neutral workflow receipt before commit.
This packet cannot complete T5 or the full goal. UI/CLI/MCP, reviewed taste,
editable handoff, cutdowns and real execution remain required followups.
