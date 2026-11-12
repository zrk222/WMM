'use strict';

function referenceLibrary() {
  const filter = (state.referenceFilter || '').toLowerCase();
  const rows = (state.workspace.references || []).filter((r) => {
    const d = r.current.data;
    return (
      `${d.title} ${d.topic} ${d.relevance_note}`.toLowerCase().includes(filter) &&
      (!state.referencePlatform || d.platform === state.referencePlatform) &&
      (!state.referenceRights || d.rights === state.referenceRights)
    );
  });
  return `<div class="section-heading"><h2>Creative source library</h2>${button('Add a reference', 'reference-add')}</div>${notice('Permitted sources are discovery evidence, not acquisition results or production assets. Unknown metrics and rights stay unknown; permission is operator supplied.')}<div class="toolbar"><input id="reference-search" aria-label="Search creative sources" placeholder="Search titles and topics" value="${esc(state.referenceFilter || '')}"><label class="field" for="reference-platform">Platform<select id="reference-platform"><option value="">All platforms</option>${['tiktok', 'youtube', 'instagram', 'linkedin', 'x', 'other'].map((p) => `<option value="${p}" ${state.referencePlatform === p ? 'selected' : ''}>${label(p)}</option>`).join('')}</select></label><label class="field" for="reference-rights">Usage rights<select id="reference-rights"><option value="">All rights states</option>${['UNKNOWN', 'REFERENCE_ONLY', 'LICENSED'].map((p) => `<option value="${p}" ${state.referenceRights === p ? 'selected' : ''}>${label(p)}</option>`).join('')}</select></label>${button('Preview source export', 'reference-import')}${button('Source CSV template', 'reference-template')}</div>${rows.length ? `<div class="record-list">${rows.map((r) => `<button class="record-row" data-action="reference-open" data-id="${esc(r.id)}"><span class="record-main"><strong>${esc(r.current.data.title)}</strong><small>${esc(label(r.current.data.platform))} Â· ${esc(r.current.data.topic)} Â· ${r.captures.length} capture versions</small><small>${r.current.data.metric_value === null ? 'Observed count unavailable' : `${r.current.data.metric_value} ${esc(label(r.current.data.metric_kind))}`} Â· ${esc(label(r.current.data.rights))}</small></span><span class="record-meta">Inspect source</span></button>`).join('')}</div>` : empty('No matching creative sources', 'Add a permitted public link or preview an approved export. Missing API access does not prevent an honest source library.', button('Add permitted source', 'reference-add'))}<div class="section-heading"><h2>Product evidence and authentic assets</h2></div>`;
}

function referenceForm(id = null) {
  const r = state.workspace.references?.find((r) => r.id === id),
    d = r?.current.data || {},
    data = { ...d, captured_at: new Date().toISOString() };
  const enums = {
    platform: ['tiktok', 'youtube', 'instagram', 'linkedin', 'x', 'other'],
    traffic_class: ['UNKNOWN', 'ORGANIC', 'PAID'],
    rights: ['UNKNOWN', 'REFERENCE_ONLY', 'LICENSED'],
    metric_kind: ['UNKNOWN', 'VIEWS', 'LIKES', 'SHARES'],
  };
  const fields = [
    field('title', data.title),
    field('post_id', data.post_id, 'text', 'Public opaque post ID; stable across refreshes'),
    field('url', data.url, 'text', 'Public HTTPS source; no private tokens'),
    field('source', data.source, 'text', 'Permitted export or collection receipt'),
    field('locale', data.locale || state.workspace.app.data.locale),
    field(
      'creator_id',
      data.creator_id,
      'text',
      'Public opaque ID, optional; no personal contacts',
      false,
    ),
    field('format', data.format, 'text', 'Observed format, e.g. product demo'),
    field('topic', data.topic),
    field(
      'relevance_note',
      data.relevance_note,
      'textarea',
      'Why this is relevant to this app; supplied assessment, not measured lift',
    ),
    field('captured_at', data.captured_at, 'text', 'Actual ISO capture time with timezone'),
    field(
      'published_at',
      data.published_at,
      'text',
      'Optional observed publication time; blank stays unknown',
      false,
    ),
    field(
      'metric_value',
      data.metric_value,
      'number',
      'Optional observed count; blank stays unavailable',
      false,
    ),
    field(
      'metric_at',
      data.metric_at,
      'text',
      'Required if a count is supplied; ISO timestamp',
      false,
    ),
    field(
      'permission_confirmed',
      false,
      'boolean',
      'Confirm permission to store this reference. This does not grant rights to copy or render.',
    ),
  ];
  for (const [name, choices] of Object.entries(enums))
    fields.push(
      `<label class="field" for="field-${name}">${esc(label(name))}<select id="field-${name}" name="${name}" required>${choices.map((v) => `<option value="${v}" ${data[name] === v ? 'selected' : ''}>${esc(label(v))}</option>`).join('')}</select></label>`,
    );
  modal(
    id ? 'Refresh source observations' : 'Add permitted reference',
    `<form id="reference-form" data-app="${esc(state.app)}" data-id="${esc(id || '')}" data-version="${r?.current.version || ''}"><div class="modal-content">${notice('Enter facts you can inspect. This saves the link and supplied observations; it does not fetch media, invent a transcript, validate rights or estimate competitor installs.')}<div class="form-grid">${fields.join('')}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save source capture</button></div></form>`,
    'CREATIVE INTELLIGENCE / SOURCE',
  );
  if (id) {
    $('#field-platform').disabled = true;
    $('#field-post_id').readOnly = true;
  }
}

async function saveReference(form) {
  const data = Object.fromEntries(new FormData(form));
  if (form.dataset.id)
    data.platform = state.workspace.references.find(
      (r) => r.id === form.dataset.id,
    ).current.data.platform;
  data.permission_confirmed = data.permission_confirmed === 'true';
  for (const key of ['published_at', 'creator_id', 'metric_at']) if (!data[key]) data[key] = null;
  data.metric_value = data.metric_value === '' ? null : Number(data.metric_value);
  const body = { data };
  if (form.dataset.id)
    Object.assign(body, { id: form.dataset.id, version: Number(form.dataset.version) });
  await api(`/api/apps/${form.dataset.app}/references`, body);
}

function openReference(id) {
  const r = state.workspace.references.find((r) => r.id === id),
    d = r.current.data;
  modal(
    d.title,
    `<div class="modal-content">${notice('Operator-supplied source; no independent permission verification, transcript, outlier score or acquisition result is inferred.')}<p>${esc(d.relevance_note)}</p><p><a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">Open original source â†—</a></p><p>${esc(label(d.platform))} Â· ${esc(d.locale)} Â· ${esc(label(d.traffic_class))} Â· ${esc(label(d.rights))}</p><p>Observed count: ${d.metric_value === null ? 'Unavailable' : `${d.metric_value} ${esc(label(d.metric_kind))}`}</p><p>Captured ${esc(d.captured_at)} Â· published ${esc(d.published_at || 'Unknown')}</p><h3>Capture history</h3>${r.captures.map((c) => `<details><summary>Version ${c.version} Â· ${esc(c.data.captured_at)}</summary><p class="app-mono">${esc(c.hash)}</p><pre>${json(c.data)}</pre></details>`).join('')}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button('Inspect source format', 'production-inspect', `data-id="${esc(id)}"`)} ${button('Refresh observations', 'reference-refresh', `data-id="${esc(id)}"`)}${button('Download source history', 'reference-download', `data-id="${esc(id)}"`)}</div>`,
    'CREATIVE INTELLIGENCE / EVIDENCE',
  );
  $('#modal .modal-actions').insertAdjacentHTML(
    'afterbegin',
    button('Review source requirements', 'capability-requirement', 'data-id="' + esc(id) + '"') +
      button('Review app fit', 'ranking-relevance', "data-id='" + esc(id) + "'"),
  );
}

function referenceImportForm() {
  modal(
    'Preview permitted source export',
    `<form id="reference-import-form" data-app="${esc(state.app)}"><div class="modal-content">${notice('Use the CSV template or an approved JSON row export, under 1 MB and at most 100 sources. Preview verifies columns, permission, dates and identities. Commit is all or none.')}<label class="field" for="reference-file">Source export<input type="file" id="reference-file" name="source_file" accept=".csv,.json" required></label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Validate and preview sources</button></div></form>`,
  );
}

async function previewReferences(form) {
  const file = new FormData(form).get('source_file');
  if (!file?.size || file.size > 1048576) throw new Error('Choose a permitted export under 1 MB.');
  const raw = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
  const body = file.name.toLowerCase().endsWith('.csv') ? { csv: raw } : { rows: JSON.parse(raw) };
  const preview = await api(`/api/apps/${form.dataset.app}/references/preview`, body);
  state.referencePreview = { ...preview, app: form.dataset.app };
  modal(
    'Review source import',
    `<div class="modal-content">${notice(preview.provenance)}${preview.conflicts.map((v) => notice(`Conflict: ${v}. Inspect and refresh the existing source before retrying the batch.`, 'warning')).join('')}<div class="table-wrap"><table class="result-table"><thead><tr><th>Source</th><th>Observation</th><th>Rights</th></tr></thead><tbody>${preview.rows.map((r) => `<tr><td>${esc(r.title)}<br>${esc(r.platform)} Â· ${esc(r.post_id)}</td><td>${r.metric_value === null ? 'Unavailable' : `${r.metric_value} ${esc(r.metric_kind)}`}</td><td>${esc(r.rights)}</td></tr>`).join('')}</tbody></table></div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button('Import previewed sources', 'reference-commit', preview.conflicts.length ? 'disabled' : '')}</div>`,
  );
}

async function referenceAction(node) {
  const id = node.dataset.id,
    action = node.dataset.action;
  const handlers = {
    'reference-add': () => referenceForm(),
    'reference-open': () => openReference(id),
    'reference-refresh': () => referenceForm(id),
    'reference-download': () =>
      download(
        `${state.app}-source.json`,
        state.workspace.references.find((r) => r.id === id),
      ),
    'reference-import': referenceImportForm,
    'reference-template': () =>
      download(
        'creative-source-template.csv',
        'platform,post_id,title,url,source,captured_at,published_at,locale,traffic_class,creator_id,format,metric_kind,metric_value,metric_at,rights,permission_confirmed,topic,relevance_note\n',
        'text/csv',
      ),
  };
  if (handlers[action]) return handlers[action]();
  if (action !== 'reference-commit') throw new Error('Unknown source action.');
  const p = state.referencePreview;
  if (!p) throw new Error('Preview the source export first.');
  await api(`/api/apps/${p.app}/references/import`, { rows: p.rows, preview_hash: p.preview_hash });
  await refresh();
  $('#modal').close();
  state.referencePreview = null;
  toast('Permitted sources imported with immutable provenance.');
}

const phaseRoles = ['HOOK', 'PROBLEM', 'STAKES', 'REVEAL', 'DEMO', 'PROOF', 'OBJECTION', 'CTA'];

function choiceField(name, options, value = '', multiple = false) {
  const titles = {
    analysis_id: 'Inspected mechanism',
    claim_ids: 'Approved claims',
    asset_ids: 'Authentic screens',
    readiness_id: 'Product readiness check',
    store_id: 'Available destination',
    route_id: 'Tested first-value route',
    duration_seconds: 'Proposed scene duration',
  };
  return `<label class="field" for="field-${esc(name)}">${esc(titles[name] || label(name))}<select id="field-${esc(name)}" name="${esc(name)}" ${multiple ? 'multiple size="4"' : ''} required>${multiple ? '' : '<option value="">Chooseâ€¦</option>'}${options.map((o) => `<option value="${esc(o.id)}" ${(Array.isArray(value) ? value.includes(o.id) : value === o.id) ? 'selected' : ''}>${esc(o.title)}</option>`).join('')}</select><small>${multiple ? 'Select the exact proof records; use Ctrl/Cmd for more than one.' : ''}</small></label>`;
}

function analysisFor(referenceId) {
  return (state.workspace.analyses || []).find((a) => a.current.data.reference_id === referenceId);
}

function inspectionForm(referenceId) {
  const source = state.workspace.references.find((r) => r.id === referenceId),
    old = analysisFor(referenceId),
    d = old?.current.data || {};
  const inputs = [
    choiceField(
      'inspection_kind',
      ['DIRECT_VIEW', 'PERMITTED_TRANSCRIPT'].map((id) => ({ id, title: label(id) })),
      d.inspection_kind,
    ),
    field(
      'inspection_confirmed',
      false,
      'boolean',
      'Confirm you actually inspected this permitted source',
    ),
    field('inspected_at', new Date().toISOString()),
    field('analyst', d.analyst),
    field('format_family', d.format_family),
    field(
      'duration_seconds',
      d.duration_seconds,
      'number',
      'Only actual directly inspected media duration; optional',
      false,
    ),
    field('uncertainty', d.uncertainty, 'textarea', 'What could not be observed or verified'),
  ];
  const phases = phaseRoles
    .map((role) =>
      phaseFields(
        role,
        d.observations?.find((o) => o.role === role),
      ),
    )
    .join('');
  modal(
    old ? 'Correct source inspection' : 'Inspect source format',
    `<form id="inspection-form" data-app="${esc(state.app)}" data-reference="${esc(referenceId)}" data-hash="${esc(source.current.hash)}" data-id="${esc(old?.id || '')}" data-version="${old?.current.version || ''}"><div class="modal-content">${notice('Open and inspect the permitted original source first. Leave unseen phases blank. Suggestions are separate from facts; transcript-only evidence cannot establish timing.')}<a href="${esc(source.current.data.url)}" target="_blank" rel="noopener noreferrer">Open original source â†—</a><div class="form-grid">${inputs.join('')}</div>${phases}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save inspected analysis</button></div></form>`,
    'CREATIVE INTELLIGENCE / INSPECTION',
  );
}

function phaseFields(role, row = {}) {
  return `<details ${role === 'HOOK' ? 'open' : ''}><summary>${esc(label(role))} Â· optional unless observed</summary><div class="form-grid">${choiceField(
    role + '_basis',
    ['OBSERVED', 'SUGGESTED'].map((id) => ({ id, title: label(id) })),
    row.basis,
  ).replace(
    ' required',
    '',
  )}${field(role + '_detail', row.detail, 'textarea', 'Blank excludes this phase', false)}${field(role + '_evidence_note', row.evidence_note, 'textarea', 'Where this was observed, or why it is a suggestion', false)}${field(role + '_start_seconds', row.start_seconds, 'number', 'Optional actual start seconds', false)}${field(role + '_end_seconds', row.end_seconds, 'number', 'Optional actual end seconds', false)}</div></details>`;
}

async function saveInspection(form) {
  const values = Object.fromEntries(new FormData(form));
  const observations = phaseRoles
    .filter((role) => values[role + '_detail']?.trim())
    .map((role) => ({
      role,
      basis: values[role + '_basis'],
      detail: values[role + '_detail'],
      evidence_note: values[role + '_evidence_note'],
      start_seconds:
        values[role + '_start_seconds'] === '' ? null : Number(values[role + '_start_seconds']),
      end_seconds:
        values[role + '_end_seconds'] === '' ? null : Number(values[role + '_end_seconds']),
    }));
  const data = {
    reference_id: form.dataset.reference,
    capture_hash: form.dataset.hash,
    inspection_kind: values.inspection_kind,
    inspection_confirmed: values.inspection_confirmed === 'true',
    inspected_at: values.inspected_at,
    analyst: values.analyst,
    format_family: values.format_family,
    duration_seconds: values.duration_seconds === '' ? null : Number(values.duration_seconds),
    observations,
    uncertainty: values.uncertainty,
  };
  const body = { data };
  if (form.dataset.id) {
    body.id = form.dataset.id;
    body.version = Number(form.dataset.version);
  }
  await api(`/api/apps/${form.dataset.app}/production/analyses`, body);
}

function productionPanel() {
  const analyses = state.workspace.analyses || [],
    briefs = state.workspace.briefs || [];
  return `${capabilitiesPanel()}${learningGuidancePanel()}<div class="section-heading"><div><h2>From inspected source to original brief</h2><p>Inspect a permitted source, bind current app proof, then prepare channel-specific work.</p></div>${button('Prepare original brief', 'production-prepare')}</div>${notice('Preparation saves original copy and a real screen plan. Local videos can be rendered below; publication and spending remain unexecuted.')}<div class="two-column"><section class="panel"><h3>Inspected mechanisms</h3>${analyses.length ? analyses.map((a) => `<div class="next-step"><div><strong>${esc(a.current.data.format_family)}</strong><p>${esc(a.source_status)} Â· ${a.current.data.observations.length} phases Â· version ${a.current.version}</p>${button('Inspect analysis', 'production-analysis', `data-id="${esc(a.id)}"`)} ${button('Correct inspection', 'production-inspect', `data-id="${esc(a.current.data.reference_id)}"`)}</div></div>`).join('') : '<p>Open a source in Evidence and choose Inspect source format. No transcript or timing is inferred.</p>'}</section><section class="panel"><h3>Original production briefs</h3>${briefs.length ? briefs.map((b) => `<div class="next-step"><div><strong>${esc(label(b.current.data.definition.channel))} Â· ${esc(b.current.data.definition.objective)}</strong><p>${esc(b.evidence_status)} Â· version ${b.current.version} Â· ${esc(briefRenderState(b))}</p>${button('Open original brief', 'production-open', `data-id="${esc(b.id)}"`)}</div></div>`).join('') : '<p>Choose current approved claims, authentic screens and tested routes. Missing evidence has a recoverable setup path.</p>'}</section></div>`;
}

function briefForm(id = null, learningId = null, preset = {}) {
  const old = state.workspace.briefs?.find((b) => b.id === id),
    d = old?.current.data.definition || preset,
    records = state.workspace.records;
  const analyses = (state.workspace.analyses || []).filter(
    (a) =>
      a.source_status === 'CURRENT' &&
      (!d.discovery || (a.id === d.analysis_id && a.current.hash === d.analysis_hash)),
  );
  if (
    d.discovery &&
    (d.discovery.manifest_version !== state.workspace.app.version || !analyses.length)
  )
    throw new Error(
      'The app or source inspection changed. Open a current research card to prepare a new brief.',
    );
  const missing = ['claim', 'asset', 'readiness', 'store', 'route'].filter(
    (kind) => !records.some((r) => r.kind === kind),
  );
  if (!analyses.length || missing.length) return productionPrerequisites(missing, !analyses.length);
  if (!analyses.some((a) => capabilityEvaluation(a.current.data.reference_id).status === 'READY'))
    return capabilitySetup();
  const channels = d.discovery ? ['SHORT_VIDEO'] : ['SHORT_VIDEO', 'LINKEDIN', 'X'];
  const selectors = [
    choiceField(
      'analysis_id',
      analyses.map((a) => ({ id: a.id, title: a.current.data.format_family })),
      d.analysis_id,
    ),
    choiceField(
      'channel',
      channels.map((id) => ({ id, title: label(id) })),
      d.channel,
    ),
  ];
  for (const kind of ['claim', 'asset', 'readiness', 'store', 'route']) {
    const key = ['claim', 'asset'].includes(kind) ? kind + '_ids' : kind + '_id';
    selectors.push(
      choiceField(
        key,
        records
          .filter((r) => r.kind === kind)
          .map((r) => ({ id: r.id, title: r.title + ' Â· ' + r.data.release })),
        d[key],
        key.endsWith('_ids'),
      ),
    );
  }
  const method = learningId ? learningProgram(learningId) : null;
  const guidance = d.discovery
    ? notice(
        'This brief carries the research cardâ€™s inspected hook and selected app proof. Keep those screens selected and write your own version of the idea. Saving prepares a brief for review. Rendering and publication are separate steps.',
      )
    : method
      ? notice(
          'This new brief will explicitly include: ' +
            method.data.definition.pattern +
            '. Existing briefs remain unchanged.',
        )
      : '';
  const fields = [
    field(
      'objective',
      d.objective,
      'textarea',
      'Specific scenario to demonstrate; a hypothesis, not a benefit claim',
    ),
    field('owner', d.owner),
    field('currency', d.currency || state.workspace.app.data.currency),
    field(
      'budget_minor',
      d.budget_minor ?? 0,
      'number',
      'Declared production cost in minor units; this authorizes no spending',
    ),
    choiceField(
      'duration_seconds',
      [15, 30, 45, 60].map((n) => ({ id: String(n), title: n + ' seconds' })),
      String(d.duration_seconds || 30),
    ),
  ];
  modal(
    old ? 'Revise original brief' : 'Prepare original brief',
    `<form id="brief-form" data-app="${esc(state.app)}" data-id="${esc(id || '')}" data-version="${old?.current.version || ''}" data-learning="${esc(learningId || '')}" data-learning-version="${method?.version || ''}" data-learning-hash="${esc(method?.hash || '')}"><div class="modal-content">${guidance}${brandBriefGuidance()}${notice('Use current release/locale evidence checked within 14 days. A newer failed readiness result blocks preparation. Imported source copy is not reused. Missing proof can be added in Evidence.')}<div class="form-grid">${selectors.join('')}${fields.join('')}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Prepare evidence-bound brief</button></div></form>`,
  );
  if (d.discovery) {
    const form = $('#brief-form');
    form.dataset.researchBinding = JSON.stringify({
      discovery: d.discovery,
      analysis_hash: d.analysis_hash,
    });
    form.tabIndex = -1;
    form.focus();
  }
}

function productionPrerequisites(missing, needsAnalysis) {
  modal(
    'Build the proof for your brief',
    `<div class="modal-content">${notice('Your work is preserved. Complete the missing setup below, then prepare a brief against current evidence. No developer configuration is required.')}${needsAnalysis ? `<h3>Inspect a permitted source</h3><p>Add a source in Evidence, open it and choose Inspect source format. Correct a stale inspection against the latest capture.</p>${button('Open source library', 'production-sources')}` : ''}${missing.map((kind) => `<div class="next-step"><div><h3>${esc(state.boot.labels[kind])}</h3><p>Add current release/locale proof. Screens require actual image upload and authenticity/rights review.</p>${kind === 'asset' ? button('Upload a real screen', 'upload') : button('Add ' + state.boot.labels[kind], 'production-evidence', `data-kind="${esc(kind)}"`)}</div></div>`).join('')}</div><div class="modal-actions">${button('Close setup guide', 'close')}</div>`,
  );
}

async function saveBrief(form) {
  const fields = new FormData(form),
    data = Object.fromEntries(fields);
  for (const key of ['claim_ids', 'asset_ids']) data[key] = fields.getAll(key);
  data.budget_minor = Number(data.budget_minor);
  data.duration_seconds = Number(data.duration_seconds);
  if (!currentWorkspace() || state.app !== form.dataset.app)
    throw new Error('Reopen the brief for the current app before saving.');
  const analysis = state.workspace.analyses.find((a) => a.id === data.analysis_id)?.current;
  if (!analysis) throw new Error('Select a current source inspection before saving.');
  data.analysis_hash = analysis.hash;
  if (form.dataset.researchBinding) {
    const saved = JSON.parse(form.dataset.researchBinding);
    if (
      saved.analysis_hash !== analysis.hash ||
      saved.discovery.manifest_version !== state.workspace.app.version
    )
      throw new Error('The app or source inspection changed. Reopen a current research card.');
    data.discovery = saved.discovery;
  }
  const body = { data };
  if (form.dataset.id) {
    body.id = form.dataset.id;
    body.version = Number(form.dataset.version);
  }
  if (form.dataset.learning) {
    const method = learningProgram(form.dataset.learning);
    if (!method?.active)
      throw new Error(
        'Learning guidance is no longer available. Inspect current Results before using it.',
      );
    await api(`/api/apps/${form.dataset.app}/learning/${method.id}/briefs`, {
      data,
      version: Number(form.dataset.learningVersion),
      hash: form.dataset.learningHash,
    });
  } else await api(`/api/apps/${form.dataset.app}/production/briefs`, body);
}

function openProduction(id, type) {
  const item = state.workspace[type].find((v) => v.id === id),
    d = item.current.data;
  const contents =
    type === 'briefs'
      ? `<h3>Original copy</h3><p class="description">${esc(d.content.copy).replaceAll('\n', '<br>')}</p><h3>Proposed scene plan</h3>${d.content.beats.map((b) => `<p><strong>${b.start_seconds}â€“${b.end_seconds}s Â· ${esc(b.scene)}</strong><br>${esc(b.script)}</p>`).join('')}<h3>Authentic screen plan</h3>${d.content.screens.map((s) => `<p>${esc(s.instruction)}</p><img class="asset-preview" src="/api/apps/${encodeURIComponent(state.app)}/files/${encodeURIComponent(s.file_id)}" alt="Selected current app screen for this proposed scene">`).join('')}<h3>Limitations</h3><ul>${d.content.limitations.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>`
      : `<p>${esc(d.uncertainty)}</p>${d.observations.map((o) => `<p><strong>${esc(o.role)} Â· ${esc(o.basis)}</strong><br>${esc(o.detail)}<br>${esc(o.evidence_note)}<br>${o.start_seconds === null ? 'Timing unavailable' : `${o.start_seconds}â€“${o.end_seconds}s`}</p>`).join('')}`;
  modal(
    type === 'briefs' ? 'Original production brief' : 'Source inspection',
    `<div class="modal-content">${notice(type === 'briefs' ? `${item.evidence_status} Â· ${briefRenderState(item)} Â· Publication NOT_RUN` : item.source_status)}${(item.findings || []).map((f) => notice(f, 'warning')).join('')}${contents}<h3>Immutable history</h3>${item.versions.map((v) => `<details><summary>Version ${v.version} Â· ${esc(v.created)}</summary><pre>${json(v.data)}</pre><p class="app-mono">${esc(v.hash)}</p></details>`).join('')}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button('Download production history', 'production-download', `data-id="${esc(id)}" data-type="${type}"`)} ${type === 'briefs' ? button('Revise brief', 'production-revise', `data-id="${esc(id)}"`) : button('Correct inspection', 'production-inspect', `data-id="${esc(d.reference_id)}"`)}</div>`,
  );
}

function productionAction(node) {
  if (node.dataset.action === 'production-evidence') return evidenceForm(node.dataset.kind);
  if (node.dataset.action === 'production-sources') {
    $('#modal').close();
    state.view = 'evidence';
    return render();
  }
  const id = node.dataset.id,
    handlers = {
      'production-inspect': () => inspectionForm(id),
      'production-analysis': () => openProduction(id, 'analyses'),
      'production-prepare': () => briefForm(),
      'production-revise': () => briefForm(id),
      'production-open': () => openProduction(id, 'briefs'),
      'production-download': () =>
        download(
          `${state.app}-production.json`,
          state.workspace[node.dataset.type].find((v) => v.id === id),
        ),
    };
  if (!handlers[node.dataset.action]) throw new Error('Unknown production action');
  return handlers[node.dataset.action]();
}
