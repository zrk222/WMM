# Approved T1 preparation scope

Owned files: packaging_contract.py, packaging_bindings.py, packaging_store.py,
db.py (one table and four triggers only), tests/test_packaging.py, scoped SSAT,
plan packet note and these CF evidence files. No public UI or production adapter.

Requirements: immutable app-scoped variants; current manifest/source/brief/product
and media reuse bindings; explicit missing evidence during ideation; script segment
hashes and original/timestamped shot plans; deny stale/foreign or malformed supplied
inputs; live stale/revoked readback; append-only history and atomic rollback.

Windows CPython 3.11 and real temporary SQLite/files are the execution profile.
Tests use synthetic assets and mocked native inspection only for the media fixture;
they prove application binding and rights behavior, not production media decoding.
Relevant native media store/brief/discovery/distribution regressions run separately.

Performance is outside this packet: no throughput/latency/scaling claim. Fixed input,
revision and page bounds are validation assertions. Accessibility is outside this
packet because no user interface changes. Other categories are applicable and
covered by named unittest cases, before-commit failure injections and killed source
mutations. These exclusions are scoped code review judgments, not platform waivers.

P2 replacement follow-up: duplicate-revision BEFORE INSERT rejects REPLACE and
INSERT OR REPLACE even with recursive_triggers=0. Real connection tests preserve
the original row bytes/hash and permit a fresh revision. No other tables changed.

Rowid follow-up: a separately named BEFORE INSERT trigger rejects existing rowids,
including replacements using a fresh composite identity. Initialization installs
this guard in databases already containing the earlier composite-key trigger.
SQLite exposes an unspecified NEW.rowid as -1 before normal automatic allocation.
Rowid -1 is therefore reserved: a manually inserted legacy -1 row blocks subsequent
automatic inserts until separately reviewed recovery. The guard deliberately fails
closed in that state. Normal generated positive rowids and fresh revisions work;
manual negative-rowid imports are outside the supported storage contract.

Draft reference shape: {kind,id,version,sha256}. Variant fields: audience, app_outcome,
title (1-300), thumbnail, opening_frame, hook, cta, sources (SOURCE/COLLECTION),
creative (BRIEF or null), app_proofs (CLAIM/ASSET). All copy is supplied draft text.
Shot list: exact VARIANT reference, script [{id,text}], shots [{id,segment_id,
segment_sha256,kind,description,source,start_ms,end_ms,assets,claims,claim_text}].
Shot kinds: A_ROLL/B_ROLL/SCREEN_RECORDING/GRAPHICS/AUDIO. Source is null for original
work and then both timestamps are null; supplied sources need increasing milliseconds.
Assets support existing ASSET evidence and current attested MEDIA originals.

Readback preserves immutable definition plus source_status CURRENT/STALE and reason,
missing_evidence (sources/creative/app_proofs; SHOT; ASSET_AND_RIGHTS; CLAIM_PROOF),
evidence_status MISSING/SUPPLIED_CURRENT/STALE. Every revision remains DRAFT with
render/publication NOT_RUN and execution_authority false. A matched claim link
requires exact approved claim text; it does not prove broader surrounding copy.

T1 does not implement shared operator/agent execution admission, UI/CLI/MCP,
preview, YouTube collection/policy, production/editor/Hypit handoff, results or
portable snapshot export/restore. T2-T7 and the original full product scope remain
required. No spending, provider call, publication, native/iOS or production claim.
Compileall is the Python build check. Ruff F rules and scoped Forge QA are lint/static
checks. Pyright is unavailable in this runtime; no static type-check pass is claimed.
