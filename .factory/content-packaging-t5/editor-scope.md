# Editable packaging handoff backend

Architecture review: reuse existing Projects.save, definition, saved_data and
render proof checks. Add optional packaging provenance to the editor definition;
existing projects retain identical serialized values. Provenance references an
exact latest SHOTS revision and owner taste revision. Bind current app, variant,
script, claim proof, source rights and policy when saving, editing and rendering.
Typed commands retain metadata; allow original-media trim, split/reorder/framing
and explicit audio, while source substitution outside the shot plan rejects.

Prepare an ordered editor definition from one explicit clip per shot, source
frame ranges/audio/role/transform/effects supplied by caller. Research timestamps
never become trims. All script segments require shots; current variant must have
authentic app proof and a brief. Save uses the existing project operation and
its request key/revision, grant and checkpoint. Do not create a second renderer.

Owned: packaging_editor.py, video_edit_contract.py, video_edit_projects.py and
tests/test_packaging_editor.py. First packet is backend-only, no claim of full
UI/CLI/MCP handoff until those controls and real render acceptance exist. Verify
old editor compatibility, exact provenance/currentness, wrong media, denied
claims/app/taste, actual project editing persistence, restart and render-admission
staleness. Run scoped CF QA/security, mutation and hash-bound workflow gates.
