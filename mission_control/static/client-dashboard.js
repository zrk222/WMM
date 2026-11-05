(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const state = { generation: 0, controllers: new Set(), clients: [], csrf: '', receipt: '', current: null, polling: null, busy: false };
  const countNames = ['queued', 'running', 'blocked', 'failed', 'succeeded', 'cancelled', 'unknown', 'interrupted', 'other'];

  function abortAll() {
    for (const controller of state.controllers) controller.abort();
    state.controllers.clear();
  }
  function clearPrivate() {
    state.clients = [];
    state.csrf = '';
    state.receipt = '';
    state.current = null;
    state.sessionMore = false;
    $('#client-select').replaceChildren();
    $('#app-select').replaceChildren();
    $('#app-select').disabled = true;
    $('#count-grid').replaceChildren();
    $('#app-name').textContent = 'Choose an app';
    $('#receipt-value').textContent = 'A receipt appears after a successful read.';
    $('#updated-value').textContent = '';
    $('#more-note').hidden = true;
    $('#workspace').hidden = true;
  }
  function clearSummary() {
    state.receipt = '';
    state.current = null;
    $('#count-grid').replaceChildren();
    $('#app-name').textContent = 'Choose an app';
    $('#receipt-value').textContent = 'A receipt appears after a successful read.';
    $('#updated-value').textContent = '';
  }
  function invalidate() {
    state.generation += 1;
    abortAll();
    clearPrivate();
    $('#logout-csrf').value = '';
    state.busy = false;
  }
  function status(title, message, mode = 'none') {
    $('#status-title').textContent = title;
    $('#status-message').textContent = message;
    $('#sign-in-form').hidden = mode !== 'login';
    $('#retry-button').hidden = mode !== 'retry';
    $('#status-card').hidden = mode === 'hide';
  }
  function request(url, options = {}, generation = state.generation) {
    const controller = new AbortController();
    state.controllers.add(controller);
    const headers = new Headers(options.headers || {});
    headers.set('Accept', 'application/json');
    return fetch(url, { ...options, headers, credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
      .then(async (response) => {
        const data = await response.json().catch(() => null);
        if (generation !== state.generation) throw new DOMException('Stale response', 'AbortError');
        if (!response.ok) {
          const error = new Error(response.status === 401 || response.status === 403 ? 'signed-out' : 'unavailable');
          error.status = response.status;
          error.url = url;
          throw error;
        }
        return { response, data };
      })
      .finally(() => state.controllers.delete(controller));
  }
  function showFailure(error) {
    invalidate();
    if (error && (error.status === 401 || error.status === 403 || error.message === 'signed-out')) {
      status('Your sign-in has ended', 'Sign in again to see your currently assigned workspaces.', 'login');
    } else if (error && error.status === 404 && error.url === '/api/session') {
      status('Workspace access changed', 'Sign in again, or ask your workspace owner to review your assignment.', 'login');
    } else {
      status('Your workspace is unavailable', 'Your private summary was cleared. Check your connection and try again.', 'retry');
    }
  }
  function keyOf(client, app) { return `${client.tenant_id}\u0000${client.client_id}\u0000${app.id}`; }
  function selected() {
    const client = state.clients.find((item) => keyOf(item, { id: '' }) === $('#client-select').value);
    const app = client?.apps.find((item) => item.id === $('#app-select').value);
    return client && app ? { client, app, key: keyOf(client, app) } : null;
  }
  function renderClients(preferredTenant, preferredClient, preferredApp) {
    const select = $('#client-select');
    select.replaceChildren();
    state.clients.forEach((client) => {
      const option = document.createElement('option');
      option.value = keyOf(client, { id: '' });
      option.textContent = client.label || client.client_id;
      select.append(option);
    });
    const wanted = state.clients.find((item) => item.tenant_id === preferredTenant && item.client_id === preferredClient);
    if (wanted) select.value = keyOf(wanted, { id: '' });
    renderApps(preferredApp);
  }
  function renderApps(preferredApp) {
    const client = state.clients.find((item) => keyOf(item, { id: '' }) === $('#client-select').value);
    const select = $('#app-select');
    select.replaceChildren();
    (client?.apps || []).forEach((app) => {
      const option = document.createElement('option');
      option.value = app.id;
      option.textContent = app.name;
      select.append(option);
    });
    select.disabled = !client?.apps?.length;
    if (client?.apps.some((app) => app.id === preferredApp)) select.value = preferredApp;
    $('#more-note').hidden = !(client?.more_available || state.sessionMore);
  }
  function paintSummary(data, receipt) {
    state.current = data;
    $('#app-name').textContent = data.app.name;
    const grid = $('#count-grid');
    grid.replaceChildren();
    for (const name of countNames) {
      const card = document.createElement('div');
      card.className = 'count';
      const value = document.createElement('span');
      value.className = 'count-value';
      value.textContent = String(data.jobs[name]);
      const label = document.createElement('span');
      label.className = 'count-label';
      label.textContent = name[0].toUpperCase() + name.slice(1);
      card.append(value, label);
      grid.append(card);
    }
    state.receipt = receipt || '';
    $('#receipt-value').textContent = state.receipt || 'No receipt reference was returned.';
    const checkedAt = new Date();
    const clockTime = $('#updated-value');
    clockTime.dateTime = checkedAt.toISOString();
    clockTime.textContent = `View checked at ${new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(checkedAt)} (your local clock)`;
    $('#workspace').hidden = false;
    $('#status-card').hidden = true;
  }
  async function loadSummary(forceGeneration) {
    if (state.busy || document.hidden) return;
    const chosen = selected();
    if (!chosen || !state.csrf) return;
    const generation = forceGeneration ?? state.generation;
    const capture = chosen.key;
    state.busy = true;
    $('#summary').setAttribute('aria-busy', 'true');
    try {
      const url = `/v1/tenants/${encodeURIComponent(chosen.client.tenant_id)}/clients/${encodeURIComponent(chosen.client.client_id)}/apps/${encodeURIComponent(chosen.app.id)}/dashboard`;
      const { response, data } = await request(url, {}, generation);
      if (generation !== state.generation || selected()?.key !== capture) return;
      paintSummary(data, response.headers.get('X-WMM-Receipt'));
    } catch (error) {
      if (error.name !== 'AbortError' && generation === state.generation) showFailure(error);
    } finally {
      if (generation === state.generation) {
        state.busy = false;
        $('#summary').setAttribute('aria-busy', 'false');
      }
    }
  }
  async function refresh() {
    invalidate();
    const generation = state.generation;
    status('Checking your access', 'This page shows assigned workspace summaries only.');
    try {
      const context = await request('/auth/context', {}, generation);
      const ctx = context.data;
      if (!ctx || typeof ctx.configured !== 'boolean' || typeof ctx.csrf !== 'string') throw new Error('unavailable');
      state.csrf = ctx.csrf;
      $('#start-csrf').value = ctx.csrf;
      $('#logout-csrf').value = '';
      if (!ctx.configured) {
        status('Sign-in is not available yet', 'Workspace access has not been configured for this service.');
        return;
      }
      const session = await request('/api/session', {}, generation);
      const data = session.data;
      if (!data || !Array.isArray(data.clients) || typeof data.csrf !== 'string') throw new Error('unavailable');
      state.csrf = data.csrf;
      state.sessionMore = Boolean(data.more_available);
      $('#logout-csrf').value = data.csrf;
      state.clients = data.clients.filter((client) => client && typeof client.tenant_id === 'string' && typeof client.client_id === 'string' && Array.isArray(client.apps));
      if (!state.clients.length) {
        clearPrivate();
        $('#workspace').hidden = false;
        status('No workspaces are assigned yet', 'Ask your Wize Marketing Machine administrator to review your workspace access.');
        return;
      }
      renderClients();
      $('#workspace').hidden = false;
      $('#more-note').hidden = !state.sessionMore;
      const chosen = selected();
      if (!chosen) {
        status('No apps are available', 'There are no assigned apps to summarize for this workspace.');
        return;
      }
      status('', '', 'hide');
      await loadSummary(generation);
    } catch (error) {
      if (error.name !== 'AbortError' && generation === state.generation) showFailure(error);
    }
  }
  $('#client-select').addEventListener('change', () => {
    state.generation += 1;
    abortAll();
    state.busy = false;
    clearSummary();
    const generation = state.generation;
    renderApps();
    const chosen = selected();
    if (chosen) { state.csrf = $('#logout-csrf').value; $('#workspace').hidden = false; loadSummary(generation); }
    else { clearPrivate(); status('No apps are available', 'There are no assigned apps to summarize for this workspace.'); }
  });
  $('#app-select').addEventListener('change', () => {
    state.generation += 1;
    abortAll();
    state.busy = false;
    clearSummary();
    const generation = state.generation;
    state.csrf = $('#logout-csrf').value;
    $('#workspace').hidden = false;
    loadSummary(generation);
  });
  $('#retry-button').addEventListener('click', refresh);
  $('#print-button').addEventListener('click', () => window.print());
  $('#export-button').addEventListener('click', () => {
    const choice = selected();
    if (!choice || !state.current) return;
    const payload = { workspace: choice.client.label || choice.client.client_id, app: state.current.app.name, jobs: state.current.jobs, receipt: state.receipt, view_checked_at: $('#updated-value').dateTime, view_checked_at_local: $('#updated-value').textContent, access: 'Read only' };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'wize-workspace-summary.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  });
  $('#logout-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const csrf = $('#logout-csrf').value;
    invalidate();
    const generation = state.generation;
    if (!csrf) {
      status('Sign-out needs a fresh check', 'Your workspace information was cleared. Try again to refresh your sign-in state.', 'retry');
      return;
    }
    const controller = new AbortController();
    state.controllers.add(controller);
    status('Signing you out', 'Your workspace information has been cleared.');
    try {
      const response = await fetch('/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ csrf }),
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'follow',
        signal: controller.signal
      });
      if (generation !== state.generation) return;
      if (!response.ok || new URL(response.url).origin !== window.location.origin) throw new Error('logout-unavailable');
      await refresh();
    } catch (error) {
      if (error.name !== 'AbortError' && generation === state.generation) {
        invalidate();
        status('Sign-out could not be confirmed', 'Your workspace information remains cleared. Try again to refresh your sign-in state.', 'retry');
      }
    } finally {
      state.controllers.delete(controller);
    }
  });
  $('#sign-in-form').addEventListener('submit', () => { invalidate(); status('Opening sign-in', 'Your assigned workspace data has been cleared.'); });
  let refreshTimer = null;
  function scheduleRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => { refreshTimer = null; refresh(); }, 120);
  }
  window.addEventListener('pageshow', scheduleRefresh);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { if (state.polling) clearInterval(state.polling); state.polling = null; }
    else { scheduleRefresh(); startPolling(); }
  });
  window.addEventListener('focus', () => { if (!document.hidden) scheduleRefresh(); });
  function startPolling() {
    if (state.polling) clearInterval(state.polling);
    state.polling = setInterval(() => { if (!document.hidden) loadSummary(); }, 30000);
  }
  startPolling();
})();
