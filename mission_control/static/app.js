'use strict';
const state = {
  boot: null,
  workspace: null,
  app: localStorage.getItem('growth-app'),
  view: 'overview',
  filter: '',
  pending: false,
};
const $ = (selector) => document.querySelector(selector);
const esc = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const json = (value) => esc(JSON.stringify(value, null, 2));
const label = (value) =>
  String(value)
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
const status = (value) =>
  `<span class="status ${esc(String(value).toLowerCase())}">${esc(label(value))}</span>`;
const notice = (text, type = '') =>
  `<div class="notice ${esc(type)}"><span aria-hidden="true">â“˜</span><span>${esc(text)}</span></div>`;
const button = (text, action, extra = '', cls = 'outline') =>
  `<button type="button" class="button ${esc(cls)}" data-action="${esc(action)}" ${extra}>${esc(text)}</button>`;
const heading = (title, description, action = '') =>
  `<div class="page-heading"><div><p class="eyebrow">${esc(state.workspace.app.data.name)} / APP GROWTH</p><h1>${esc(title)}</h1><p class="description">${esc(description)}</p></div>${action}</div>`;
const empty = (title, description, action = '') =>
  `<div class="empty-state"><div class="empty-icon" aria-hidden="true">â†—</div><h3>${esc(title)}</h3><p>${esc(description)}</p>${action}</div>`;

async function api(path, body, options = {}) {
  const headers = body
    ? { 'Content-Type': 'application/json', 'X-CSRF-Token': state.boot?.csrf }
    : {};
  const method = options.method || (body ? 'POST' : 'GET');
  let response, result;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      ...options,
    });
  } catch (error) {
    throw WMMFeedback.error(error, { interrupted: true, method });
  }
  try {
    result = await response.json();
  } catch (error) {
    throw WMMFeedback.error(error, { unreadable: true, status: response.status, method });
  }
  if (!response.ok)
    throw WMMFeedback.error(new Error(result.error || `Request failed (${response.status})`), {
      ...result,
      status: response.status,
      method,
    });
  return result;
}

function toast(message) {
  const node = $('#toast');
  node.textContent = message;
  node.hidden = false;
  delete node.dataset.error;
  node.setAttribute('role', 'status');
  node.removeAttribute('tabindex');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (node.hidden = true), 6000);
}

function showActionError(error) {
  const issue = WMMFeedback.error(error);
  let inline = $('#form-error');
  if (!inline && $('#modal')?.open) {
    inline = document.createElement('div');
    inline.id = 'form-error';
    inline.className = 'field-error';
    $('#modal-body').prepend(inline);
  }
  const node = inline || $('#toast');
  clearTimeout(toast.timer);
  node.innerHTML = WMMFeedback.view(issue);
  node.setAttribute('role', 'alert');
  node.setAttribute('tabindex', '-1');
  node.hidden = false;
  if (!inline) {
    node.dataset.error = 'true';
    node.insertAdjacentHTML('beforeend', button('Dismiss message', 'dismiss-operation-error'));
  }
  node.focus();
}

async function initialize() {
  try {
    state.boot = await api('/api/bootstrap');
    state.research = await api('/api/research');
    if (!state.boot.apps.some((a) => a.id === state.app)) state.app = state.boot.apps[0]?.id;
    $('#app-select').innerHTML = state.boot.apps
      .map((a) => `<option value="${esc(a.id)}">${esc(a.data.name)}</option>`)
      .join('');
    $('#app-select').value = state.app;
    await refresh();
  } catch (error) {
    $('#main').innerHTML =
      `${notice(error.message, 'error')}${empty('Your workspace could not load', 'Your saved records are preserved. Check the local server and retry.', button('Retry loading', 'reload'))}`;
  }
}

async function refresh() {
  if (!state.app) return;
  const app = state.app,
    generation = (state.refreshGeneration = (state.refreshGeneration || 0) + 1);
  if (!currentWorkspace()) {
    state.workspace = null;
    state.workspaceError = '';
    $('#app-name').textContent =
      state.boot.apps.find((item) => item.id === app)?.data.name || 'Selected app';
    render();
  }
  let workspace;
  try {
    workspace = await api(`/api/apps/${encodeURIComponent(app)}`);
  } catch (error) {
    if (state.app !== app || state.refreshGeneration !== generation) return;
    if (currentWorkspace()) throw error;
    state.workspaceError = error.message;
    render();
    return;
  }
  if (state.app !== app || state.refreshGeneration !== generation) return;
  state.workspace = workspace;
  state.workspaceError = '';
  state.workspaceObservedAt = new Date().toISOString();
  localStorage.setItem('growth-app', app);
  $('#app-name').textContent = state.workspace.app.data.name;
  render();
  return { app, generation, workspace };
}

function currentWorkspace() {
  return Boolean(state.app && state.workspace?.app?.id === state.app);
}

function render() {
  WMMTelemetry.clear();
  WMMAgentControl.invalidate(state);
  WMMCompleteAutomation.invalidate(state);
  WMMVideoEditor.invalidate(state);
  WMMStudio.invalidate(state);
  WMMMedia.invalidate(state);
  WMMDrive.invalidate(state);
  WMMDiscovery.invalidate(state);
  WMMOrganicResearch.invalidate(state);
  window.WMMOrganicPolicy?.invalidate(state);
  WMMPackaging.invalidate(state);
  WMMFunnels.invalidate(state);
  WMMAppleAnalytics.invalidate(state);
  WMMOneSignal.invalidate(state);
  window.WMMPublicationUI?.invalidate(state);
  $('#edit-app').disabled = !currentWorkspace();
  document.querySelectorAll('.nav-item').forEach((node) => {
    node.classList.toggle('active', node.dataset.view === state.view);
    if (node.dataset.view === state.view) node.setAttribute('aria-current', 'page');
    else node.removeAttribute('aria-current');
  });
  if (!currentWorkspace()) {
    $('#main').setAttribute('aria-busy', state.workspaceError ? 'false' : 'true');
    $('#main').innerHTML = state.workspaceError
      ? `${notice(state.workspaceError, 'error')}${empty('This app could not load', 'Your saved work is preserved. Retry loading this app.', button('Retry this app', 'retry-workspace'))}`
      : `<div role="status">${empty('Loading this app', 'Your workspace will appear here when it is ready.')}</div>`;
    return;
  }
  $('#main').setAttribute('aria-busy', 'false');
  const views = {
    weekly: weeklyView,
    overview: goalOverview,
    workflow: guidedView,
    pipeline: pipelineView,
    evidence: evidenceView,
    results: resultsView,
    connections: connectionsView,
    agents: agentAccessView,
    activity: activityView,
    research: researchView,
  };
  $('#main').innerHTML = views[state.view]();
  if (['agents', 'activity'].includes(state.view))
    $('#main .page-heading').insertAdjacentHTML(
      'afterend',
      WMMAgentControl.panel(state, verifiedOwnerNext(state.workspace, 'connect an agent')),
    );
  if (['agents', 'activity'].includes(state.view))
    $('#main .page-heading').insertAdjacentHTML(
      'afterend',
      WMMCompleteAutomation.panel(state, verifiedOwnerNext(state.workspace, 'manage automation')),
    );
  if (state.view === 'research')
    $('#main .page-heading').insertAdjacentHTML('afterend', WMMVideoEditor.panel());
  if (state.view === 'research')
    $('#main .page-heading').insertAdjacentHTML('afterend', WMMStudio.panel());
  if (state.view === 'research')
    $('#main .page-heading').insertAdjacentHTML(
      'afterend',
      WMMOrganicResearch.panel() +
        (window.WMMOrganicPolicy?.panel() || '') +
        WMMDiscovery.panel() +
        WMMPackaging.panel(state) +
        WMMMedia.panel() +
        WMMDrive.panel(),
    );

  automationDecorateWorkflow();
  WMMPageReports.decorate(state, document);
  if (state.view === 'overview') {
    $('#goal-advanced')?.insertAdjacentHTML('beforebegin', WMMOrganicResearch.entry());
    const report = $('#main .page-reporting');
    if (report) $('#goal-advanced > summary').insertAdjacentElement('afterend', report);
  }
  if (['workflow', 'agents', 'activity', 'research'].includes(state.view)) {
    $('#main .page-heading').insertAdjacentHTML('afterend', WMMTelemetry.panel());
    WMMTelemetry.mount(growthReviewServices());
  }
  window.WMMPublicationUI?.mount(state, growthReviewServices());
}

function summary() {
  const w = state.workspace,
    ready = w.stages.filter((s) => s.status === 'READY').length;
  return `<div class="summary-grid"><div class="summary-card"><p class="metric-label">Stages with required evidence</p><div class="metric-value">${ready}<small> / 12</small></div><p class="metric-note">Local readiness, not publication</p></div><div class="summary-card"><p class="metric-label">Evidence & assets</p><div class="metric-value">${w.records.length}</div><p class="metric-note">Versioned and scoped to this app</p></div><div class="summary-card"><p class="metric-label">Authorized ad spending</p><div class="metric-value">0<small> authorized</small></div><p class="metric-note">Provider changes require exact approval</p></div></div>`;
}

function stageCard(stage) {
  return `<button class="stage-card" data-action="stage" data-id="${stage.id}"><div class="stage-top"><span class="stage-number">${String(stage.id).padStart(2, '0')} / ${esc(stage.group.toUpperCase())}</span>${status(stage.status === 'READY' ? 'READY' : 'NEEDS_INPUT')}</div><h3>${esc(stage.title)}</h3><p>${esc(stage.description)}</p><div class="stage-bottom"><span>${stage.missing.length ? `${stage.missing.length} next checks` : 'Ready to prepare'}</span><span aria-hidden="true">â†—</span></div></button>`;
}

function flow() {
  return `<div class="flow-line">${['Plan', 'Launch', 'Learn'].map((name, i) => `<div class="flow-phase"><span class="phase-number">${i + 1}</span><span>${name}<small>${['Establish the truth', 'Prepare the experiment', 'Measure useful growth'][i]}</small></span></div>`).join('')}</div>`;
}

function detailedOverview() {
  const w = state.workspace,
    next = w.stages.find((s) => s.status !== 'READY') || w.stages[10];
  const recent = w.jobs.slice(0, 3);
  return `<section class="hero"><div><p class="eyebrow">WIZE MARKETING MACHINE</p><h1>Plan your app marketing.<br>Prepare the work.<br>Measure results.</h1><p>Designed for your personal AI agent to operate on your behalf, with permissions you control and verified results reported back to you. You can inspect, edit and operate the same workspace yourself. Turn your app details, audience research, video references and analytics into a marketing plan you can act on. Wize Marketing Machine organizes creative briefs, video editing work, app store checks and subscription experiments. You receive saved work packets, approval records and PDF reports showing the evidence, results and next actions for each app. Use them to shorten creative turnaround, reduce repeated work and find conversion bottlenecks. Your business targets are more useful installs, stronger paid conversion and retention, and less wasted acquisition cost; measure actual gains in your app results.</p><button type="button" class="button light" data-view="workflow">Open Guided workflow â†’</button></div><div class="hero-art" aria-hidden="true"><div class="orbit"></div><div class="orbit second"></div><div class="orbit third">â†—</div></div></section>${summary()}${automaticPreparationPanel()}<div class="two-column"><section class="panel"><p class="eyebrow">YOUR NEXT BEST ACTION</p><h2>${esc(next.title)}</h2><div class="next-step"><div class="step-icon" aria-hidden="true">${next.id}</div><div><h3>${esc(next.missing[0] || 'Review a mature experiment')}</h3><p>${esc(next.description)}</p>${button('Open this stage', 'stage', `data-id="${next.id}"`)}</div></div></section><section class="panel"><p class="eyebrow">RECENT RUNS</p><h2>Work you can inspect</h2>${recent.length ? recent.map((job) => `<div class="next-step"><div><h3>${job.action === 'pipeline' ? 'Pipeline preparation' : job.action === 'experiment' ? 'Experiment analysis' : 'Provider read'}</h3><p>${esc(new Date(job.created).toLocaleString())}</p>${status(job.status)} <button class="text-button" data-action="job" data-id="${esc(job.id)}">View result â†—</button></div></div>`).join('') : `<p class="description">Your first run will create a saved packet for every stage, including the evidence still needed.</p><button class="text-button" data-view="pipeline">Explore the pipeline â†—</button>`}</section></div><div class="section-heading"><div><h2>A clear path from plan to learning</h2><p>Twelve connected stages. Each one has a purpose.</p></div><button class="text-button" data-view="pipeline">View all stages â†’</button></div>${flow()}<div class="stage-grid">${w.stages.slice(0, 3).map(stageCard).join('')}</div>`;
}

function pipelineView() {
  return `${heading('Your growth pipeline', 'Prepare the work, inspect the evidence, and keep the next step visible.', button('Prepare all 12 stages', 'run-all', '', ''))}${summary()}${automaticPreparationPanel()}${flow()}<div class="stage-grid">${state.workspace.stages.map(stageCard).join('')}</div>`;
}

function evidenceView() {
  const records = state.workspace.records.filter((r) =>
    `${r.title} ${r.kind}`.toLowerCase().includes(state.filter.toLowerCase()),
  );
  return `${heading('Evidence before confidence', 'Keep your app facts, authentic captures and experiment data together.', button('ï¼‹ Add evidence', 'add-evidence', '', ''))}<div class="toolbar"><input id="evidence-search" aria-label="Search evidence" placeholder="Search titles or evidence types" value="${esc(state.filter)}">${button('Upload image', 'upload')}${button('Export workspace', 'export')}${button('Restore snapshot', 'restore')}</div>${notice('Records are operator-reported unless clearly labeled as a provider observation. No private conversations or credentials belong here.')}${spyTokPanel()}${spiraPanel()}${referenceLibrary()}${records.length ? `<div class="record-list">${records.map(recordRow).join('')}</div>` : empty('Start with one useful proof', 'Add a current journey test, an approved claim, a screenshot or a mature cohort. Each item keeps its source and version.', button('Add your first evidence', 'add-evidence'))}`;
}

function recordRow(record) {
  return `<button class="record-row" data-action="record" data-id="${esc(record.id)}"><span class="record-icon" aria-hidden="true">${record.kind === 'asset' ? 'â–§' : 'â–±'}</span><span class="record-main"><strong>${esc(record.title)}</strong><small>${esc(state.boot.labels[record.kind] || record.kind)} Â· ${esc(record.provenance)} Â· v${record.version}</small></span><span class="record-meta">${esc(new Date(record.updated).toLocaleDateString())}<br>Open â†—</span></button>`;
}

function money(value, currency) {
  if (value === null || value === undefined) return 'Unavailable';
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || 'USD',
    }).format(value / 100);
  } catch {
    return `${value} minor units`;
  }
}
function percent(value) {
  return value === null || value === undefined ? 'Unavailable' : `${(value * 100).toFixed(1)}%`;
}

let modalReturnFocus = null;
function modalFocusable() {
  const dialog = $('#modal');
  if (!dialog) return [];
  return [
    ...dialog.querySelectorAll(
      'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
    ),
  ].filter((node) => node.getClientRects().length > 0);
}
function modalTab(event) {
  if (event.key !== 'Tab') return;
  const dialog = $('#modal');
  if (!dialog?.open) return;
  const items = modalFocusable();
  if (!items.length) {
    event.preventDefault();
    dialog.focus();
    return;
  }
  const first = items[0],
    last = items[items.length - 1],
    active = document.activeElement;
  if (event.shiftKey && (active === first || !dialog.contains(active))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
    event.preventDefault();
    first.focus();
  }
}
function modal(title, html, eyebrow = 'WORKSPACE') {
  if (!$('#modal').open) {
    const active = document.activeElement;
    modalReturnFocus = active === document.body ? null : active;
  }
  WMMAppleAnalytics.clear();
  WMMOneSignal.clear();
  WMMAgentControl.clear();
  WMMCompleteAutomation.clear();
  WMMVideoEditor.clear();
  WMMStudio.clear();
  WMMMedia.clear();
  WMMDrive.clear();
  WMMDiscovery.clear();
  WMMOrganicResearch.clear();
  window.WMMOrganicPolicy?.clear();
  WMMPackaging.clear();
  WMMFunnels.clear();
  $('#modal-title').textContent = title;
  $('#modal-eyebrow').textContent = eyebrow;
  $('#modal-body').innerHTML = html;
  $('#modal-body').insertAdjacentHTML('afterbegin', WMMStories.dialog(title, html));
  if (currentWorkspace()) automationAttach();
  if (!$('#modal').open) $('#modal').showModal();
  $('#modal').focus();
}

function openStage(id) {
  const s = state.workspace.stages.find((item) => item.id === Number(id));
  if (s.missing.length && resolutionIssues(s.id).length) return openResolutionStage(s.id);
  const checklist = s.missing.length
    ? s.missing.map((m) => `<div class="detail-item blocked-item">${esc(m)}</div>`).join('')
    : notice(
        "The supplied inputs meet this local stage's checks. Review the packet before external action.",
      );
  modal(
    s.title,
    `<div class="modal-content"><p class="description">${esc(s.description)}</p><div class="details-list">${checklist}</div><h3>What to do</h3><ol>${s.operations.tasks.map((task) => `<li>${esc(task)}</li>`).join('')}</ol><p><strong>Deliverable:</strong> ${esc(s.operations.deliverable)}</p><p><strong>How to verify:</strong> ${esc(s.operations.verify)}</p><h3>Evidence for this stage</h3><div class="toolbar">${s.inputs
      .filter((k) => k !== 'manifest')
      .map((k) => button(`ï¼‹ ${state.boot.labels[k]}`, 'add-evidence', `data-kind="${esc(k)}"`))
      .join(
        '',
      )}${s.id === 1 ? button('Edit app setup', 'edit-app') : ''}</div><details><summary>Dependencies and evidence boundary</summary><p class="description">${s.dependencies.length ? `Stages ${s.dependencies.join(', ')} must meet their input checks.` : 'This is the starting stage.'} Operator-reported readiness is separate from provider approval and public availability.</p></details></div><div class="modal-actions">${button('Prepare this stage', 'run-stage', `data-id="${s.id}"`, '')}</div>`,
    `STAGE ${String(s.id).padStart(2, '0')} / ${s.group.toUpperCase()}`,
  );
}

function field(name, value = '', type = 'text', hint = '', mandatory = true, title = label(name)) {
  const id = `field-${name}`;
  let input = `<input id="${id}" name="${esc(name)}" value="${esc(value)}" ${type === 'number' ? 'type="number" min="0" step="1"' : type === 'date' ? 'type="date"' : 'type="text"'} required>`;
  if (type === 'boolean')
    input = `<select id="${id}" name="${esc(name)}" required><option value="">Chooseâ€¦</option><option value="true" ${value === true ? 'selected' : ''}>Yes</option><option value="false" ${value === false ? 'selected' : ''}>No</option></select>`;
  if (type === 'textarea' || type === 'json')
    input = `<textarea id="${id}" name="${esc(name)}" class="${type === 'json' ? 'json-field' : ''}" required>${esc(type === 'json' && typeof value === 'object' ? JSON.stringify(value, null, 2) : value)}</textarea>`;
  if (!mandatory) input = input.replaceAll(' required', '');
  return `<label class="field ${type === 'textarea' || type === 'json' ? 'full' : ''}" for="${id}">${esc(title)}${input}${hint ? `<small>${esc(hint)}</small>` : ''}</label>`;
}

function appForm(isNew = false) {
  if (!isNew && !currentWorkspace()) return toast('Wait for this app to load, then reopen setup.');
  const app = isNew ? { id: '', data: {}, version: null } : state.workspace.app;
  const workspaceId = field(
    'id',
    app.id,
    'text',
    isNew
      ? 'Leave blank to generate one from the app name. Saved IDs cannot change.'
      : 'Saved workspace IDs cannot change.',
    !isNew,
    'Workspace ID',
  );
  const essentials = [
    field('name', app.data.name, 'text', '', true, 'App name'),
    field('audience', app.data.audience, 'text', 'Who needs this app most?', true, 'Who it helps'),
    field(
      'job',
      app.data.job,
      'textarea',
      'Describe the problem the app solves.',
      true,
      'What it helps them do',
    ),
    field(
      'activation',
      app.data.activation,
      'text',
      'For example, finish a first coaching session.',
      true,
      'First useful action',
    ),
    field(
      'release',
      app.data.release,
      'text',
      'Enter the version or build you plan to promote.',
      true,
      'App version or build',
    ),
    field(
      'locale',
      app.data.locale,
      'text',
      'Use a locale you tested, for example en-US.',
      true,
      'App locale',
    ),
  ];
  const fields = [
    field('currency', app.data.currency, 'text', 'Optional until economics are supplied', false),
    field('website', app.data.website, 'text', 'Optional public app website', false),
  ];
  fields.push(
    ...['brand_voice', 'brand_visual', 'brand_source', 'brand_boundaries'].map((key) =>
      field(
        key,
        app.data[key] || '',
        'textarea',
        'Optional operator-supplied brand guidance; use a source and avoid unsupported promises',
        false,
      ),
    ),
  );
  fields.push(automationPreferenceFields(app.data));
  fields.push(
    field(
      'store_app_id',
      app.data.store_app_id || '',
      'text',
      'Optional numeric App Store app ID; required for subscription catalog reads',
      false,
    ),
  );
  fields.push(
    field(
      'android_package',
      app.data.android_package || '',
      'text',
      'Optional Android application ID. Google Play setup can discover it from your project metadata.',
      false,
    ),
  );
  fields.push(
    field(
      'android_track',
      app.data.android_track || '',
      'text',
      'Set with the Android package, for example production or internal. Changes invalidate prior read scope.',
      false,
    ),
  );
  fields.push(
    field(
      'social_callback_base_url',
      app.data.social_callback_base_url || '',
      'text',
      'Optional verified HTTPS relay origin. Prefills official social callbacks; Mission Control stays private.',
      false,
    ),
  );
  const setup = isNew
    ? `<div class="form-grid">${essentials.join('')}</div><details><summary>Optional settings</summary><p>Add these now or return to App setup later.</p><div class="form-grid">${workspaceId}${fields.join('')}</div></details>`
    : `<div class="form-grid">${workspaceId}${essentials.join('')}${fields.join('')}</div>`;
  modal(
    isNew ? 'Add your app' : 'App setup',
    `<form id="app-form" data-new="${isNew}"><div class="modal-content">${setup}<div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">${isNew ? 'Save and choose a goal' : 'Save app setup'}</button></div></form>`,
  );
  if (!isNew) $('#field-id').readOnly = true;
  if (!isNew)
    $('#app-form .modal-content').insertAdjacentHTML(
      'afterbegin',
      `<section class="panel"><h3>Let the agent collect app details</h3><p>Read the saved public website, compare its suggestions and approve only the fields you want to change.</p>${button('Discover app details', 'setup-open')}</section>`,
    );
}

const booleanFields = new Set([
  'authentic',
  'rights_cleared',
  'consent_review',
  'refund_reconciliation',
  'installed',
  'fresh_install',
  'signed_out',
  'restore_tested',
  'trial_eligibility_tested',
  'mature',
  'confirmed',
]);
const numberFields = new Set([
  'p0_count',
  'price_minor',
  'budget_minor',
  'daily_cap_minor',
  'eligible',
  'retained',
  'installs',
  'activated',
  'paid',
  'acquisition_cost_minor',
  'net_proceeds_minor',
  'delivery_cost_minor',
  'refunds_minor',
  'amount_minor',
  'rating',
]);
const longFields = new Set([
  'claim',
  'hypothesis',
  'guardrails',
  'change',
  'heldout_test',
  'rollback',
  'fallback',
]);

function evidenceForm(kind = 'readiness', record = null, preset = {}) {
  if (kind === 'acquisition' && !record) return acquisitionForm('asa');
  const data = record?.data || preset;
  const options = Object.entries(state.boot.labels)
    .map(
      ([key, value]) =>
        `<option value="${esc(key)}" ${key === kind ? 'selected' : ''}>${esc(value)}</option>`,
    )
    .join('');
  const fields = state.boot.fields[kind]
    .filter((name) => kind !== 'readiness' || name !== 'result')
    .map((name) => {
      const type =
        name === 'analysis'
          ? 'json'
          : booleanFields.has(name)
            ? 'boolean'
            : numberFields.has(name)
              ? 'number'
              : longFields.has(name)
                ? 'textarea'
                : 'text';
      let value = data[name] ?? '';
      if (name === 'release' && !value) value = state.workspace.app.data.release || '';
      if (name === 'locale' && !value) value = state.workspace.app.data.locale || '';
      if (name === 'checked_at' && !value) value = new Date().toISOString();
      const hint =
        name === 'result'
          ? 'Use PASS only after the stated checks pass; otherwise FAIL or NOT_RUN'
          : name === 'availability'
            ? 'AVAILABLE requires a current public readback'
            : name === 'env_ref'
              ? 'Variable name only. Never paste a token.'
              : '';
      return field(name, value, type, hint);
    });
  modal(
    record ? 'Inspect and update evidence' : 'Add evidence',
    `<form id="evidence-form" data-kind="${esc(kind)}" data-id="${esc(record?.id || '')}"><div class="modal-content"><div class="form-grid"><label class="field full" for="evidence-kind">Evidence type<select id="evidence-kind">${options}</select></label>${field('title', record?.title || '')}${field('source', record?.source || '', 'text', 'Receipt, report, test path or public URL; no secrets')}${fields.join('')}</div>${record ? `<details><summary>Source hash and version</summary><p class="app-mono">${esc(record.hash)} Â· version ${record.version}</p></details>` : ''}<div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save evidence</button></div></form>`,
  );
  if (kind === 'readiness') {
    $('#form-error').insertAdjacentHTML('beforebegin', journeyFields(data));
    wireJourneys(data);
  }
  if (record) $('#evidence-kind').disabled = true;
  if (kind === 'asset')
    $('#modal-body .modal-content').insertAdjacentHTML(
      'afterbegin',
      notice(
        'Upload the actual PNG/JPEG first. Authenticity and rights are human review assertions; a file hash alone does not prove either.',
      ),
    );
}

function acquisitionForm(mode) {
  const types = `<label class="field full" for="worksheet-mode">Worksheet type<select id="worksheet-mode"><option value="asa" ${mode === 'asa' ? 'selected' : ''}>Apple Ads bid worksheet</option><option value="aeo" ${mode === 'aeo' ? 'selected' : ''}>Answer-engine observation</option></select></label>`;
  const asa = [
    field('cohort_id'),
    field('currency', state.workspace.app.data.currency),
    field('taps', '', 'number'),
    field('paid', '', 'number'),
    field(
      'contribution_per_payer_minor',
      '',
      'number',
      "Refund-adjusted contribution in cents or the currency's minor units",
    ),
    field('contribution_horizon', '', 'text', 'For example D30; use a mature measured horizon'),
    field('acquisition_share', '', 'text', 'Fraction 0 to 1 for acquisition allocation'),
    field('non_media_cost_per_tap_minor', '', 'number'),
    field(
      'owner_cpt_cap_minor',
      '',
      'number',
      'Planning ceiling; this does not authorize spending',
    ),
    field('mature', '', 'boolean'),
    field('counts_verified', '', 'boolean'),
    field('contribution_verified', '', 'boolean'),
  ];
  const aeo = [
    field('engine', '', 'text', 'Record the actual engine/API and search mode'),
    field('locale', state.workspace.app.data.locale),
    field('query_id'),
    field('observation_id', crypto.randomUUID()),
    field('observed_at', new Date().toISOString()),
    field('mention', '', 'boolean'),
    field('citation', '', 'boolean'),
    field(
      'correct_citation',
      '',
      'boolean',
      'Yes only after inspecting whether the cited source backs the claim',
    ),
    field('citation_url', '', 'text', 'Public HTTPS source when a citation exists', false),
  ];
  modal(
    'Add ASA / AEO evidence',
    `<form id="evidence-form" data-kind="acquisition" data-worksheet="${mode}" data-id=""><div class="modal-content">${notice('This worksheet uses your supplied evidence. It does not verify the provider, authorize bids or claim rankings.')}<div class="form-grid">${types}${field('title')}${field('source', '', 'text', 'Report or captured-answer receipt; no secrets')}${(mode === 'asa' ? asa : aeo).join('')}</div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save and calculate worksheet</button></div></form>`,
  );
}

function openRecord(id) {
  const record = state.workspace.records.find((r) => r.id === id);
  evidenceForm(record.kind, record);
  if (record.kind === 'asset' && record.data.file_id)
    $('#modal-body .modal-content').insertAdjacentHTML(
      'afterbegin',
      `<img class="asset-preview" src="/api/apps/${encodeURIComponent(state.app)}/files/${encodeURIComponent(record.data.file_id)}" alt="Uploaded asset: ${esc(record.title)}">`,
    );
}

function openProvider(id) {
  const provider = state.boot.providers.find((p) => p.id === id);
  if (id === 'aeo') return acquisitionForm('aeo');
  modal(
    `Connect ${provider.name}`,
    `<div class="modal-content">${notice('Connection tests only read data; no campaign or metadata writes occur.')}<p class="description">${esc(provider.setup)}</p><div class="details-list"><div class="detail-item"><strong>1. Prepare the credential on your server</strong><p>Use an app-specific environment variable beginning GROWTH_${esc(state.app.toUpperCase().replaceAll('-', '_'))}_ . Restart Mission Control after changing its environment.</p></div><div class="detail-item"><strong>2. Save the binding</strong><p>Enter the variable name, the exact organization/account ID and this app's Store ID.</p></div><div class="detail-item"><strong>3. Test read access</strong><p>Inspect the saved provider response. A configured binding alone is not a working connection.</p></div></div></div><div class="modal-actions">${button('Enter connection details', 'add-connection', `data-id="${esc(id)}"`, '')}</div>`,
  );
}

async function queue(action, data) {
  const app = state.app;
  const job = await api(`/api/apps/${app}/jobs`, {
    action,
    data,
    request_key: crypto.randomUUID(),
  });
  if (state.app !== app) return;
  toast('Run saved. Its result will appear in Activity.');
  await refresh();
  if (state.app !== app) return;
  openJob(job.id);
  pollJob(job.id);
}

async function pollJob(id) {
  const app = state.app;
  for (let attempt = 0; attempt < 40; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 750));
    if (!state.workspace.jobs.some((j) => j.id === id)) return;
    await refresh();
    if (state.app !== app) return;
    const job = state.workspace.jobs.find((j) => j.id === id);
    if (!job) return;
    if ($('#modal').open && $('#modal-body').dataset.job === id) openJob(id);
    if (!['QUEUED', 'RUNNING'].includes(job.status)) {
      toast(
        job.status === 'SUCCEEDED'
          ? "Run finished. Inspect each stage's result."
          : 'Run needs attention. Its reason is saved.',
      );
      return;
    }
  }
  toast('Run is still pending. Check Activity for its saved state.');
}

function currentInventoryRun(job, binding) {
  return (
    job.status === 'SUCCEEDED' &&
    job.action === 'sync' &&
    !job.data.options &&
    job.app_id === state.app &&
    job.data.connection_id === binding.id &&
    job.data.connection_version === binding.version
  );
}

function verifiedCampaignInventory(binding) {
  const job = state.workspace.jobs.find((item) => currentInventoryRun(item, binding));
  const result = job?.result;
  if (
    result?.api_version !== 'PLATFORM_V1' ||
    result.app_id !== state.app ||
    result.store_app_id !== binding.data.store_app_id ||
    result.account_id !== binding.data.account_id
  )
    return null;
  const rows = result.payload?.data;
  if (!Array.isArray(rows) || rows.length > 100) return null;
  if (
    rows.some(
      (row) =>
        !row ||
        row.promotedObjectType !== 'APPSTORE_APP' ||
        String(row.promotedObjectId) !== binding.data.store_app_id ||
        String(row.adAccountId) !== binding.data.account_id ||
        !/^\d{1,30}$/.test(String(row.id)),
    )
  )
    return null;
  if (!Number.isInteger(result.payload.total_count) || result.payload.total_count < rows.length)
    return null;
  if (!['COMPLETE', 'PARTIAL'].includes(result.coverage)) return null;
  if ((result.coverage === 'COMPLETE') !== (result.payload.total_count === rows.length))
    return null;
  return result;
}

function campaignPicker(binding) {
  const inventory = verifiedCampaignInventory(binding);
  if (!inventory)
    return notice(
      'Use Test read access to load a saved campaign list, or enter known IDs below. Every report checks current app and account scope again.',
    );
  const rows = inventory.payload.data;
  if (!rows.length)
    return notice(
      'The saved access check found no campaigns for this app. This does not prove ad eligibility or delivery. You can enter a known ID for a fresh scoped read.',
    );
  const options = rows
    .map(
      (row) =>
        `<option value="${esc(String(row.id))}">${esc(String(row.id))} â€” ${esc(typeof row.name === 'string' ? row.name : 'Campaign ' + row.id)}</option>`,
    )
    .join('');
  return `<section class="notice"><p>Saved access check: ${esc(inventory.observed_at)}. Showing ${rows.length} of ${esc(String(inventory.payload.total_count))} campaigns. ${inventory.coverage === 'PARTIAL' ? 'This is a partial list; use known IDs for other campaigns.' : 'The saved page was complete.'} A report rechecks current scope.</p><label class="field" for="verified-campaign">Choose a saved campaign<select id="verified-campaign"><option value="">Choose a campaignâ€¦</option>${options}</select></label><button type="button" class="button secondary" id="add-verified-campaign" disabled>Add campaign to report</button></section>`;
}

function wireCampaignPicker() {
  const picker = $('#verified-campaign'),
    add = $('#add-verified-campaign');
  if (!picker || !add) return;
  picker.addEventListener('change', () => {
    add.disabled = !picker.value;
  });
  add.addEventListener('click', () => {
    const input = $('#field-campaign_ids');
    const ids = [
      ...new Set(
        input.value
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
      ),
    ];
    if (!ids.includes(picker.value)) ids.push(picker.value);
    if (ids.length > 20) {
      $('#form-error').textContent = 'Choose at most 20 distinct campaign IDs per report.';
      return;
    }
    input.value = ids.join(',');
    $('#form-error').textContent = '';
  });
}

function releaseInventoryPanel() {
  const release = state.workspace.release_inventory;
  const binding = state.workspace.records.find(
    (r) =>
      r.kind === 'connection' &&
      r.data.provider === 'app_store' &&
      r.data.auth_mode !== 'disconnected',
  );
  if (!release || release.state === 'NOT_APPLICABLE') return '';
  const selected = release.selection;
  const action = binding
    ? button('Inspect App Store release', 'release-inventory', `data-id="${esc(binding.id)}"`)
    : button('Connect App Store Connect', 'provider', 'data-id="app_store"');
  return `<section class="panel" id="release-inventory-panel" aria-labelledby="release-inventory-heading"><h2 id="release-inventory-heading">Release being promoted</h2>${status(release.state)}<p>${esc(release.reason)}</p>${selected ? `<p>Apple ${esc(selected.version)} Â· build ${esc(selected.build_number || 'not selected')} Â· ${esc(selected.locale)}<br><small>Local release: ${esc(selected.local_release)}</small></p>` : ''}<p class="description">A complete inventory is one prerequisite. Public availability, screenshot authenticity and billing need separate proof.</p><div class="toolbar">${action}${release.job_id ? button('Inspect selected-release read', 'job', `data-id="${esc(release.job_id)}"`) : ''}</div></section>`;
}

function releaseForm(id, saved = null) {
  const binding = state.workspace.records.find(
    (r) => r.id === id && r.kind === 'connection' && r.data.provider === 'app_store',
  );
  if (!binding || binding.data.auth_mode === 'disconnected')
    throw new Error("Reconnect this app's App Store connection first.");
  const job = state.workspace.jobs.find((j) => currentInventoryRun(j, binding)),
    result = job?.result;
  const owned =
    result?.provider === 'app_store' &&
    result.app_id === state.app &&
    String(result.payload?.data?.id) === binding.data.store_app_id;
  const versions =
    owned && Array.isArray(result.payload.included)
      ? result.payload.included.filter(
          (r) => r.type === 'appStoreVersions' && /^[A-Za-z0-9-]{1,80}$/.test(r.id) && r.attributes,
        )
      : [];
  const choices = versions
    .map(
      (r) =>
        `<option value="${esc(r.id)}" ${saved?.version_id === r.id ? 'selected' : ''}>${esc(r.attributes.versionString)} Â· ${esc(r.attributes.platform)} Â· ${esc(label(r.attributes.appStoreState))}</option>`,
    )
    .join('');
  modal(
    'Inspect App Store release',
    `<form id="release-inventory-form" data-app="${esc(state.app)}" data-connection="${esc(id)}" data-version="${binding.version}"><div class="modal-content">${notice('Read-only inspection of metadata and screenshot file inventory. This does not submit, approve or change your app.')}${owned ? `<p>Version list observed ${esc(result.observed_at)}. The read will verify ownership again.</p>` : notice("Test read access to load this app's version list, or enter a known release ID below.")}<label class="field" for="release-version">Select a release<select id="release-version" name="version_id"><option value="">Choose a version</option>${choices}</select></label><details><summary>Use a known release ID</summary><label class="field" for="release-manual">App Store version resource ID<input id="release-manual" name="manual_version_id" autocomplete="off" maxlength="80" value="${esc(saved?.version_id && !versions.some((r) => r.id === saved.version_id) ? saved.version_id : '')}"></label></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Read release inventory</button></div></form>`,
  );
}

function releaseResult(report) {
  const job = state.workspace.jobs.find(
    (row) => row.status === 'SUCCEEDED' && row.result === report,
  );
  const select = job
    ? button('Use this release for promotion', 'release-select', `data-id="${esc(job.id)}"`)
    : '';
  const locales = report.locales
    .map(
      (row) =>
        `<details><summary>${esc(row.locale || 'Locale not supplied')} Â· ${esc(row.coverage)} Â· ${row.screenshot_sets.reduce((n, s) => n + s.screenshots.length, 0)} files observed</summary>${row.missing_fields.length ? notice('Missing metadata: ' + row.missing_fields.join(', '), 'warning') : ''}${row.screenshot_sets.length ? row.screenshot_sets.map((set) => `<h3>${esc(set.display_type || 'Display type not supplied')} Â· ${esc(set.coverage)}</h3><ol>${set.screenshots.map((file) => `<li><strong>${esc(file.filename || 'Filename unavailable')}</strong> Â· ${esc(file.delivery_state || 'Delivery not supplied')} Â· ${esc(file.width ?? '?')} Ã— ${esc(file.height ?? '?')}<small>Checksum: ${esc(file.checksum || 'Unavailable')}</small></li>`).join('')}</ol>`).join('') : notice('No screenshot sets observed; partial coverage does not prove there are none.')}<details><summary>Observed metadata</summary><pre>${json(row.metadata)}</pre></details></details>`,
    )
    .join('');
  return `${status(report.coverage)}<h3>Version ${esc(report.version)} Â· ${esc(report.platform)}</h3><p>${esc(label(report.review_state || 'Not supplied'))} Â· Build ${esc(report.build?.number || 'not selected / unavailable')}</p><p>Observed ${esc(report.observed_at)} Â· ${report.requests} source requests</p>${notice(report.interpretation)}${select}${report.coverage === 'PARTIAL' ? notice('Some resources were not inspected. Do not treat this as a complete release check.', 'warning') : ''}${locales || notice('No localizations were returned.', 'warning')}<details><summary>Exact inventory and source hashes</summary><pre>${json(report)}</pre></details>`;
}

async function selectPromotionRelease(node) {
  const app = state.app,
    job = state.workspace.jobs.find((row) => row.id === node.dataset.id),
    report = job?.result;
  if (!job || !report || report.operation !== 'release_inventory')
    throw new Error('Reopen a current saved release inventory.');
  const body = {
    manifest_version: state.workspace.app.version,
    connection_id: job.data.connection_id,
    connection_version: job.data.connection_version,
    job_id: job.id,
    report_hash: report.source_hash,
  };
  node.disabled = true;
  try {
    await api(`/api/apps/${encodeURIComponent(app)}/release-selection`, body);
    if (state.app !== app) return;
    await refresh();
    $('#modal').close();
    state.view = 'connections';
    render();
    $('#release-inventory-panel').scrollIntoView({ block: 'start' });
    toast('Promotion release saved locally. Review the current prerequisites.');
  } finally {
    node.disabled = false;
  }
}

function reportForm(id, saved = null) {
  const binding = state.workspace.records.find((r) => r.id === id);
  if (!binding)
    throw new Error('This connection is unavailable. Reconnect from this app workspace.');
  if (binding.data.provider === 'app_store' && saved?.operation === 'release_inventory')
    return releaseForm(id, saved);
  if (binding.data.provider === 'app_store')
    return queue('sync', {
      connection_id: id,
      options: {
        operation: saved?.operation === 'subscription_catalog' ? 'subscription_catalog' : 'reviews',
      },
    });
  const end = new Date(),
    start = new Date(end);
  start.setUTCDate(start.getUTCDate() - 7);
  const reports = {
    campaign_report: 'Campaign report',
    keyword_report: 'Keyword report',
    search_term_report: 'Search-term report',
  };
  const choices = `<label class="field" for="field-operation">Report type<select id="field-operation" name="operation">${Object.entries(
    reports,
  )
    .map(
      ([key, title]) =>
        `<option value="${key}" ${saved?.operation === key ? 'selected' : ''}>${title}</option>`,
    )
    .join('')}</select></label>`;
  modal(
    'Read Apple Ads report',
    `<form id="provider-report-form" data-app="${esc(state.app)}" data-connection="${esc(id)}" data-version="${binding.version}"><div class="modal-content">${notice('Selected campaigns must belong to this exact app and ad account. This read cannot change a campaign or spend money.')}<p id="report-timezone" role="status"></p>${campaignPicker(binding)}<div class="form-grid">${choices}${field('campaign_ids', saved?.campaign_ids?.join(',') || '', 'text', 'Separate 1â€“20 numeric IDs with commas')}${field('start', saved?.start || start.toISOString().slice(0, 10), 'date', 'Calendar date in the selected reporting timezone; last 90 days')}${field('end', saved?.end || end.toISOString().slice(0, 10), 'date', 'Calendar date in the selected reporting timezone; no future dates')}</div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Read campaign report</button></div></form>`,
  );
  const update = () => {
    const name = $('#field-operation').value;
    $('#provider-report-form [type=submit]').textContent = 'Read ' + reports[name].toLowerCase();
    $('#report-timezone').textContent =
      name === 'search_term_report'
        ? 'Account reporting timezone (ORTZ). Low-volume terms may be suppressed or aggregated; fetched rows are not total demand.'
        : 'UTC reporting window. Provider-attributed installs do not prove paid customers.';
  };
  $('#field-operation').addEventListener('change', update);
  update();
  wireCampaignPicker();
}

function providerResult(result) {
  if (result.operation === 'release_inventory') return releaseResult(result);
  if (result.operation === 'subscription_catalog') return subscriptionResult(result);
  if (result.provider === 'app_store' && result.store_impressions)
    return WMMAppleAnalytics.impressionsResult(result);
  if (!Array.isArray(result.rows)) return `<pre>${json(result)}</pre>`;
  const review = result.operation === 'reviews';
  const keyword = result.operation === 'keyword_report',
    search = result.operation === 'search_term_report';
  const rows = result.rows
    .map((r) =>
      review
        ? `<tr><td>${esc(r.rating)} / 5</td><td><strong>${esc(r.title)}</strong><p>${esc(r.body)}</p><small>${esc(r.createdDate)} Â· ${esc(r.territory)}</small></td></tr>`
        : `<tr><td>${esc(search ? r.metadata.searchTermText : keyword ? r.metadata.text : r.metadata.name || r.metadata.id)}${keyword || search ? `<small>Campaign ${esc(r.metadata.campaignId)} Â· ${esc(keyword ? r.metadata.matchType : r.metadata.keyword?.text || 'No targeting keyword supplied')}</small>` : ''}</td><td>${esc(r.totalMetrics.taps ?? 'Unavailable')}</td><td>${esc(r.totalMetrics.totalInstalls ?? 'Unavailable')}</td><td>${esc(r.totalMetrics.localSpend?.amount ?? 'Unavailable')} ${esc(r.totalMetrics.localSpend?.currency || '')}</td></tr>`,
    )
    .join('');
  return `${status(result.coverage)}${notice(result.interpretation, result.coverage === 'PARTIAL' ? 'warning' : 'info')}<p>${result.rows.length} observed rows Â· ${result.pages} fetched pages${result.reporting_timezone ? ` Â· ${esc(result.reporting_timezone)}` : ''}</p>${result.rows.length ? `<div class="table-wrap"><table class="result-table"><thead><tr>${review ? '<th>Rating</th><th>Unverified public complaint</th>' : `<th>${search ? 'Observed search term' : keyword ? 'Targeting keyword' : 'Campaign'}</th><th>Taps</th><th>Provider-attributed installs</th><th>Reported spend</th>`}</tr></thead><tbody>${rows}</tbody></table></div>` : notice('No matching provider rows were returned. This does not prove that the product is healthy or the campaign effective.')}<details><summary>Inspect dates, source hashes and exact observed data</summary><pre>${json(result)}</pre></details>`;
}

function openJob(id) {
  const job = state.workspace.jobs.find((j) => j.id === id);
  const reportWaiting =
    job?.action === 'sync' &&
    job.status === 'SUCCEEDED' &&
    job.result?.status === 'WAITING_FOR_REPORTS';
  if (!reportWaiting && state.workspace.jobs.some((j) => j.id === id && j.action === 'agent_run'))
    return agentOpenRun(id);
  if (!reportWaiting && state.workspace.resolutions?.history.some((r) => r.job_id === id))
    return openResolutionRun(id);
  if (!job) return toast('This run is outside the current history. Refresh the selected app.');
  if (
    !reportWaiting &&
    job.action === 'sync' &&
    ['play_releases', 'play_subscriptions'].includes(job.data.options?.operation)
  )
    return playOpenJob(job);
  const outputs = reportWaiting ? [] : job.result?.outputs || [];
  let content = notice(
    'This run is saved locally. Prepared packets are not provider publication or measured acquisition.',
  );
  if (job.result?.error && !reportWaiting) content += notice(job.result.error, 'error');
  content += outputs.map((output) => stagePacketCard(output, id)).join('');
  if (job.result && !outputs.length)
    content +=
      (reportWaiting ? WMMTelemetry.waitingResultMarkup(job.result) : providerResult(job.result)) +
      button('Download observed result', 'download-report', `data-id="${esc(id)}"`);
  if (job.action === 'sync' && job.data.options && !['RUNNING', 'QUEUED'].includes(job.status))
    content += button('Run report again', 'rerun-report', `data-id="${esc(id)}"`);
  const runState = outputs.length
    ? `<p>Saved preparation Â· ${esc(new Date(job.created).toLocaleString())}. Buttons open the current workflow; the drafts below retain this run's saved inputs.</p><details><summary>Run reference</summary>${status(job.status)}<p class="app-mono">${esc(id)}</p></details>`
    : `${status(job.status)}<p class="app-mono">${esc(id)}</p>`;
  modal(
    outputs.length ? 'Your prepared workflow' : 'Saved run',
    `<div class="modal-content">${runState}${content}</div><div class="modal-actions">${['RUNNING', 'QUEUED'].includes(job.status) ? button('Cancel local run', 'cancel-job', `data-id="${esc(id)}"`) : button('Close result', 'close')}</div>`,
    outputs.length ? 'SAVED WORKFLOW' : 'RUN HISTORY',
  );
  $('#modal-body').dataset.job = id;
}

function prepareReview() {
  const records = state.workspace.records.filter((r) =>
    ['distribution', 'store', 'experiment'].includes(r.kind),
  );
  if (!records.length) return toast('Add a distribution, store or experiment record first.');
  modal(
    'Prepare an immutable review',
    `<form id="review-form"><div class="modal-content">${notice('The packet freezes exact source contents for 24 hours. External execution remains manual.')}<label class="field" for="review-record">Source record<select name="record_id" id="review-record">${records.map((r) => `<option value="${esc(r.id)}">${esc(r.title)}</option>`).join('')}</select></label><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Prepare review packet</button></div></form>`,
  );
}

function openReview(id) {
  const review = state.workspace.approvals.find((r) => r.id === id);
  modal(
    'Review exact contents',
    `<div class="modal-content">${status(review.status)}${notice(`Prepared by ${review.preparer}. Current local operator: ${state.boot.operator}. A different reviewer must inspect this packet before recording review.`)}<pre>${json(review.packet)}</pre><p class="app-mono">SHA256 ${esc(review.hash)}</p><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions">${button('Download handoff', 'download-review', `data-id="${esc(id)}"`)}${review.status === 'WAITING_REVIEW' ? button('Record independent review', 'record-review', `data-id="${esc(id)}"`, '') : ''}</div>`,
  );
}

function download(name, data, contentType = 'application/json') {
  const url = URL.createObjectURL(
    new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], {
      type: contentType,
    }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function serverDownload(path, name) {
  const link = document.createElement('a');
  link.href = path;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

document.addEventListener('click', async (event) => {
  const node = event.target.closest('[data-action],[data-view],[data-report-page]');
  if (!node) return;
  if (node.hasAttribute('data-report-page')) {
    try {
      WMMPageReports.openReport(WMMPageReports.model(state), window, node);
    } catch (error) {
      showActionError(error);
    }
    return;
  }
  const view =
    node.dataset.view || (node.dataset.action === 'research-channel-open' ? 'research' : null);
  if (view) {
    state.weeklyGeneration = (state.weeklyGeneration || 0) + 1;
    state.weeklyLoading = false;
    state.view = view;
    render();
    $('#main').focus();
    return;
  }
  if (node.dataset.action === 'dismiss-operation-error') {
    $('#toast').hidden = true;
    return;
  }
  if (node.dataset.action?.startsWith('weekly-')) {
    try {
      await weeklyAction(node);
    } catch (error) {
      showActionError(error);
    }
    return;
  }
  try {
    await handleAction(node);
  } catch (error) {
    showActionError(error);
  }
});
document.addEventListener('submit', formSubmit);
document.addEventListener('change', (event) => {
  if (event.target.id === 'install-export-file' && event.target.closest('#install-import-form'))
    return installImportDetect(event.target.closest('#install-import-form'));
  if (event.target.closest('#publication-draft-form'))
    return WMMPublicationUI.change(
      event.target.closest('#publication-draft-form'),
      growthReviewServices(),
      event.target,
    );
  if (event.target.closest('.funnel-workspace'))
    return WMMFunnels.change(event.target, growthReviewServices());
  if (event.target.id === 'reference-platform') {
    state.referencePlatform = event.target.value;
    render();
  }
  if (event.target.id === 'reference-rights') {
    state.referenceRights = event.target.value;
    render();
  }
  if (event.target.id === 'evidence-kind') evidenceForm(event.target.value);
  if (event.target.id === 'worksheet-mode') acquisitionForm(event.target.value);
});
$('#app-select').addEventListener('change', async (event) => {
  state.app = event.target.value;
  state.filter = '';
  state.installImport = null;
  $('#modal').close();
  $('#modal-body').replaceChildren();
  try {
    await refresh();
  } catch (error) {
    toast(error.message);
  }
});
$('#add-app').addEventListener('click', () => appForm(true));
$('#edit-app').addEventListener('click', () => appForm(false));
$('#close-modal').addEventListener('click', () => $('#modal').close());
$('#modal').addEventListener('close', () => {
  const dialog = $('#modal');
  // The close event is queued. A newer dialog or focus choice takes precedence.
  if (dialog.open) return;
  WMMAppleAnalytics.clear();
  WMMOneSignal.clear();
  WMMAgentControl.clear();
  WMMCompleteAutomation.clear();
  WMMVideoEditor.clear();
  WMMStudio.clear();
  WMMMedia.clear();
  WMMDrive.clear();
  WMMDiscovery.clear();
  WMMOrganicResearch.clear();
  WMMPackaging.clear();
  WMMFunnels.clear();
  delete $('#modal-body').dataset.job;
  const target = modalReturnFocus;
  modalReturnFocus = null;
  const active = document.activeElement;
  if (target?.isConnected && (active === document.body || dialog.contains(active))) target.focus();
});
$('#modal').addEventListener('keydown', modalTab);
document.addEventListener('keydown', (event) => {
  const dialog = $('#modal');
  if (event.key === 'Escape' && dialog?.open && dialog.contains(event.target)) {
    event.preventDefault();
    dialog.close();
  }
});
document.addEventListener('input', (event) => {
  if (event.target.id === 'reference-search') {
    const position = event.target.selectionStart;
    state.referenceFilter = event.target.value;
    render();
    $('#reference-search').focus();
    $('#reference-search').setSelectionRange(position, position);
    return;
  }
  if (event.target.closest('#experiment-form')) return samplePreview();
  if (event.target.id !== 'evidence-search') return;
  const position = event.target.selectionStart;
  state.filter = event.target.value;
  render();
  $('#evidence-search').focus();
  $('#evidence-search').setSelectionRange(position, position);
});
$('#asset-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 8388608) throw new Error('Choose an image smaller than 8 MB.');
    const response = await fetch(`/api/apps/${state.app}/files`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': state.boot.csrf, 'X-Filename': encodeURIComponent(file.name) },
      body: file,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    await refresh();
    openRecord(result.id);
    toast('Image saved. Review authenticity, rights, device and release before use.');
  } catch (error) {
    toast(error.message);
  } finally {
    event.target.value = '';
  }
});
$('#restore-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 33554432)
      throw new Error('Snapshot exceeds 32 MB; use a filesystem backup for larger workspaces.');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
    const result = await api('/api/restore', {}, { body: text });
    state.app = result.id;
    await initialize();
    toast('Snapshot restored. Existing workspaces were preserved.');
  } catch (error) {
    toast(error.message);
  } finally {
    event.target.value = '';
  }
});
$('#event-file').addEventListener('change', async (event) => {
  const input = event.target,
    file = input.files[0];
  if (!file) return;
  const app = input.dataset.app,
    cohort = input.dataset.cohort;
  try {
    if (file.size > 1048576)
      throw new Error('Use a smaller export under 1 MB and 500 rows per batch.');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
    const body = { cohort_id: cohort };
    if (file.name.toLowerCase().endsWith('.csv')) body.csv = text;
    else {
      const decoded = JSON.parse(text);
      if (decoded.cohort_id && decoded.cohort_id !== cohort)
        throw new Error('This file names a different cohort. Select the matching cohort first.');
      body.events = Array.isArray(decoded) ? decoded : decoded.events;
    }
    const result = await api(`/api/apps/${encodeURIComponent(app)}/events`, body);
    if (state.app === app) await refresh();
    toast(
      `${result.inserted} events imported; ${result.duplicates} unchanged duplicates. Inspect reconciliation before drawing conclusions.`,
    );
  } catch (error) {
    toast(error.message);
  } finally {
    input.value = '';
  }
});
initialize();
$('#modal').addEventListener('close', () => {
  if (!$('#modal').open) window.WMMOrganicPolicy?.clear();
});
document.addEventListener(
  'invalid',
  (event) => window.WMMOrganicPolicy?.validation(event.target, growthReviewServices(), true),
  true,
);
document.addEventListener('input', (event) =>
  window.WMMOrganicPolicy?.validation(event.target, growthReviewServices()),
);
document.addEventListener(
  'invalid',
  (event) => WMMOrganicResearch.validation(event.target, growthReviewServices(), true),
  true,
);
document.addEventListener('input', (event) =>
  WMMOrganicResearch.validation(event.target, growthReviewServices()),
);
