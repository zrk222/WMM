import { WMMPublicationUI } from './publication.mjs';
import {
  acquisitionForm,
  appForm,
  evidenceForm,
  evidenceView,
  takeModalReturnFocus,
  modalTab,
  openRecord,
  pipelineView,
} from './app-ui.mjs';
import { activityView, researchView } from './app-research.mjs';
import { agentAccessView } from './agent-access.mjs';
import { automationDecorateWorkflow } from './workflow-automation.mjs';
import { connectionsView } from './app-connections.mjs';
import { formSubmit, handleAction } from './app-events.mjs';
import { goalOverview, guidedView } from './guided-workflow.mjs';
import { growthReviewServices, resultsView, samplePreview } from './app-results.mjs';
import { installImportDetect } from './app-install.mjs';
import { verifiedOwnerNext } from './verified-review.mjs';
import { weeklyAction, weeklyView } from './app-weekly.mjs';
import {
  WMMOrganicPolicy,
  WMMAgentControl,
  WMMAppleAnalytics,
  WMMCompleteAutomation,
  WMMDiscovery,
  WMMDrive,
  WMMFeedback,
  WMMFunnels,
  WMMMedia,
  WMMOneSignal,
  WMMOrganicResearch,
  WMMPackaging,
  WMMPageReports,
  WMMStudio,
  WMMTelemetry,
  WMMVideoEditor,
} from './feature-apis.mjs';
('use strict');
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
  WMMOrganicPolicy?.invalidate(state);
  WMMPackaging.invalidate(state);
  WMMFunnels.invalidate(state);
  WMMAppleAnalytics.invalidate(state);
  WMMOneSignal.invalidate(state);
  WMMPublicationUI?.invalidate(state);
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
        (WMMOrganicPolicy?.panel() || '') +
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
  WMMPublicationUI?.mount(state, growthReviewServices());
}

function summary() {
  const w = state.workspace,
    ready = w.stages.filter((s) => s.status === 'READY').length;
  return `<div class="summary-grid"><div class="summary-card"><p class="metric-label">Stages with required evidence</p><div class="metric-value">${ready}<small> / 12</small></div><p class="metric-note">Local readiness, not publication</p></div><div class="summary-card"><p class="metric-label">Evidence & assets</p><div class="metric-value">${w.records.length}</div><p class="metric-note">Versioned and scoped to this app</p></div><div class="summary-card"><p class="metric-label">Authorized ad spending</p><div class="metric-value">0<small> authorized</small></div><p class="metric-note">Provider changes require exact approval</p></div></div>`;
}

let started = false;
function startApplication() {
  if (started) return;
  started = true;
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
    const target = takeModalReturnFocus();
    const active = document.activeElement;
    if (target?.isConnected && (active === document.body || dialog.contains(active)))
      target.focus();
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
    if (!$('#modal').open) WMMOrganicPolicy?.clear();
  });
  document.addEventListener(
    'invalid',
    (event) => WMMOrganicPolicy?.validation(event.target, growthReviewServices(), true),
    true,
  );
  document.addEventListener('input', (event) =>
    WMMOrganicPolicy?.validation(event.target, growthReviewServices()),
  );
  document.addEventListener(
    'invalid',
    (event) => WMMOrganicResearch.validation(event.target, growthReviewServices(), true),
    true,
  );
  document.addEventListener('input', (event) =>
    WMMOrganicResearch.validation(event.target, growthReviewServices()),
  );
}

export {
  state,
  $,
  esc,
  json,
  label,
  status,
  notice,
  button,
  heading,
  empty,
  api,
  toast,
  showActionError,
  initialize,
  refresh,
  currentWorkspace,
  render,
  summary,
  startApplication,
};
