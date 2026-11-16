/* Owner-managed Apple inventory and refresh controls; no provider writes. */
(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.WMMAppleAnalytics = value;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const esc = (v) =>
    String(v ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  const button = (text, action, extra = '') =>
    `<button type="button" class="button outline" data-action="apple-analytics-${action}" ${extra}>${esc(text)}</button>`;
  let active = null;
  function scope(state) {
    const w = state.workspace || {},
      app = w.app || {},
      id = w.identity || {},
      role = (w.access?.members || []).find(
        (m) => m.principal === id.principal && m.status === 'ACTIVE',
      );
    const bindings = (w.records || [])
      .filter(
        (r) =>
          r.kind === 'connection' &&
          r.data?.provider === 'app_store' &&
          r.data?.store_app_id === app.data?.store_app_id &&
          r.data?.auth_mode !== 'disconnected',
      )
      .map((r) => [r.id, r.version, r.hash])
      .sort((a, b) => String(a[0]).localeCompare(String(b[0])));
    return {
      app: state.app,
      workspace: app.id,
      version: app.version,
      store: app.data?.store_app_id ?? null,
      principal: id.principal,
      status: id.status,
      expires: id.expires_at_epoch,
      identityRef: w.identity || null,
      role: role?.role,
      roleVersion: role?.version,
      csrf: state.boot?.csrf,
      bindings,
    };
  }
  const same = (a, b) => a.identityRef === b.identityRef && JSON.stringify(a) === JSON.stringify(b);
  function clear() {
    active = null;
  }
  function invalidate(state) {
    if (active && !same(active.scope, scope(state))) clear();
  }
  function current(t) {
    return (
      active === t &&
      same(t.scope, scope(t.d.state)) &&
      t.node?.isConnected &&
      t.d.document.querySelector('#modal')?.open
    );
  }
  function panel() {
    return `<section class="panel" aria-label="Apple analytics"><p class="eyebrow">APP STORE / ANALYTICS</p><h2>Keep Apple analytics current</h2><p>Check report availability and choose whether to refresh the downloads report. Missing report instances do not mean zero downloads.</p>${button('Review Apple analytics', 'open')}</section>`;
  }
  function show(d, title, html, data = null) {
    d.modal(
      title,
      `<div id="apple-analytics-root" class="modal-content">${html}<p id="apple-analytics-status" role="status" aria-live="polite"></p><p id="apple-analytics-error" class="field-error" role="alert"></p></div>`,
      'APP STORE / ANALYTICS',
    );
    active = {
      d,
      scope: scope(d.state),
      node: d.document.querySelector('#apple-analytics-root'),
      data,
      pending: false,
    };
    return active;
  }
  function friendly(value) {
    return value ? String(value).replaceAll('_', ' ') : 'Not recorded';
  }
  function time(value, epoch = false) {
    if (value === null || value === undefined || value === '') return 'Not recorded';
    const d = new Date(epoch ? Number(value) * 1000 : value);
    return Number.isNaN(d.getTime()) ? 'Not recorded' : d.toLocaleString();
  }
  const canRead = (data) => data?.connection?.status === 'CONFIGURED_UNVERIFIED';
  const detailedName = 'App Downloads Detailed';
  function inventoryNextStep(data) {
    if (data.connection?.status === 'RECONNECT_REQUIRED')
      return 'Reconnect the App Store Connect key for this app, then read Apple inventory again.';
    if (data.connection?.status === 'PROTECTED_STORAGE_UNAVAILABLE')
      return 'Unlock protected storage on this host, then read Apple inventory again.';
    if (!data.connection) return 'Connect App Store Connect for this app and read its inventory.';
    switch (data.inventory?.status) {
      case 'REPORT_SETUP_REQUIRED':
        return 'Apple did not return an active report stream. Ask an App Store Connect Admin to start ongoing reporting for this app. Keep your existing Sales and Reports key in WMM, then read Apple inventory again.';
      case 'REQUEST_INVENTORY_PARTIAL':
        return 'Apple returned an incomplete list of report requests. Read Apple inventory again before deciding whether setup is needed.';
      case 'WAITING_FOR_REPORTS':
        return 'Apple showed an active report stream with no available files in the saved inventory. First reports usually take 24–48 hours after setup. Read Apple inventory later. No file means the download count is unknown.';
      default:
        return '';
    }
  }
  function inventoryGuidance(data) {
    const next = inventoryNextStep(data);
    if (!next) return '';
    const docs =
      canRead(data) && data.inventory?.status === 'REPORT_SETUP_REQUIRED'
        ? ' <a href="https://developer.apple.com/help/app-store-connect-analytics/overview/analytics-reports-api" target="_blank" rel="noopener noreferrer">Apple’s report setup instructions (opens in a new tab)</a>.'
        : '';
    return `<p><strong>Next step:</strong> ${esc(next)}${docs}</p>`;
  }
  function campaignForm(data) {
    const report = data.reports?.find((r) => r.name === detailedName && r.coverage === 'COMPLETE');
    if (!report)
      return '<p>For campaign downloads, generate the Apple campaign link in App Store Connect and refresh the inventory until App Downloads Detailed is available.</p>';
    const days = (report.daily || []).map((day) => day.processing_date).sort();
    const latest = days.at(-1);
    const recommended = days.find((day) => Date.parse(latest) - Date.parse(day) <= 6 * 86400000);
    const collect =
      canRead(data) && data.inventory?.job_id && latest
        ? `<p id="apple-campaign-processing-note">Choose up to 31 Apple file processing days. Files may include earlier download dates or corrections.</p>
<div class="field"><label for="apple-campaign-file-start">File processing start</label><input id="apple-campaign-file-start" name="file_start" type="date" value="${esc(recommended)}" min="${esc(days[0])}" max="${esc(latest)}" aria-describedby="apple-campaign-processing-note"></div>
<div class="field"><label for="apple-campaign-file-end">File processing end (included)</label><input id="apple-campaign-file-end" name="file_end" type="date" value="${esc(latest)}" min="${esc(days[0])}" max="${esc(latest)}"></div>
<button class="button outline" type="submit" value="collect" formnovalidate>Collect Detailed files</button>`
        : '<p>No daily Detailed file is ready to collect with this connection.</p>';
    return `<details><summary>Measure App Store campaign downloads</summary><p>Use the link Apple generated for this app. Apple may suppress low-volume results. First-time downloads are not website sessions or first opens.</p><form id="apple-campaign-form"><div class="field"><label for="apple-campaign-link">Apple campaign link</label><input id="apple-campaign-link" name="link" type="url" required maxlength="2048"></div>${collect}<div class="field"><label for="apple-campaign-territory">Storefront country code (two letters)</label><input id="apple-campaign-territory" name="territory" maxlength="2" pattern="[A-Za-z]{2}" placeholder="CA" required></div><div class="field"><label for="apple-campaign-start">Start date</label><input id="apple-campaign-start" name="start" type="date" required></div><div class="field"><label for="apple-campaign-end">End date (included)</label><input id="apple-campaign-end" name="end" type="date" required></div><button type="submit" class="button" value="review">Review saved downloads</button></form><div id="apple-campaign-results"></div></details>`;
  }
  function campaignResults(result) {
    const rows = result.rows
      .map(
        (row) =>
          `<tr><td>${esc(row.date)}</td><td>${esc(row.first_time_downloads ?? 'Unknown')}</td><td>${esc(row.source_sha256 ?? 'No saved file')}</td></tr>`,
      )
      .join('');
    return `<h3>Apple-reported first-time downloads · ${esc(result.territory)}</h3><div class="table-wrap"><table class="result-table"><thead><tr><th scope="col">Date</th><th scope="col">Reported downloads</th><th scope="col">Source fingerprint</th></tr></thead><tbody>${rows}</tbody></table></div><p>${esc(result.next_action)}</p>`;
  }
  function details(data) {
    const s = data.schedule,
      reports = data.reports || [],
      options = reports.filter((r) => r.name === 'App Downloads Standard');
    const discovery = reports.find(
      (r) => r.name === 'App Store Discovery and Engagement Standard' && r.coverage === 'COMPLETE',
    );
    const impressions =
      discovery && canRead(data)
        ? button('Collect store impressions', 'impressions') +
          '<p>Read the latest daily Apple discovery file. Activity shows the counts Apple supplied for each report row. Unique counts can overlap across rows.</p>'
        : '';
    const state = s
      ? `<p><strong>Refresh:</strong> ${esc(friendly(s.status))} · ${s.enabled ? 'On' : 'Off'}<br>Last job: ${esc(s.last_job || 'Not recorded')} · ${esc(s.last_job_status ? friendly(s.last_job_status) : 'No status')} · Failures: ${esc(s.failures)}<br>Last metrics collected: ${esc(time(s.last_success))} · Next due: ${s.enabled ? esc(time(s.next_due, true)) : 'Not scheduled'}</p>${['BLOCKED', 'FAILED'].includes(s.last_job_status) ? '<p>Inspect the latest refresh and repair the reported issue before trying again.</p>' : ''}${s.last_job ? button('Inspect latest refresh', 'job') : ''}`
      : '<p>No saved refresh schedule.</p>';
    const rows = reports
      .map(
        (r) =>
          `<li>${esc(r.name)}: ${esc(r.instance_count)} report instances · ${esc(friendly(r.coverage))}</li>`,
      )
      .join('');
    const selects = options
      .map(
        (r) =>
          `<option value="${esc(r.id)}" ${s?.report_id === r.id ? 'selected' : ''}>${esc(r.name)}</option>`,
      )
      .join('');
    const form = options.length
      ? `<form id="apple-analytics-form"><div class="field"><label for="apple-analytics-report">Report</label><select id="apple-analytics-report" name="report_id" required>${selects}</select></div><div class="field"><label for="apple-analytics-interval">Refresh every (hours)</label><input id="apple-analytics-interval" type="number" name="interval_hours" min="24" max="168" step="1" value="${esc(s?.interval_hours || 24)}" required></div><button class="button" type="submit">${s?.enabled ? 'Save refresh settings' : 'Enable refresh'}</button></form>`
      : '<p>Read the current inventory to choose the App Downloads Standard report.</p>';
    const source = data.connection
      ? data.inventory
        ? 'Saved for this app. The successful inventory below records access at that time, not a guarantee of current access.'
        : 'Saved for this app. No successful current-source inventory is recorded.'
      : 'Not connected for this app.';
    const controls = canRead(data)
      ? button('Read Apple inventory', 'inventory')
      : data.connection?.status === 'PROTECTED_STORAGE_UNAVAILABLE'
        ? '<p>Unlock protected storage on this host, then refresh saved status.</p>'
        : button(
            data.connection ? 'Reconnect App Store Connect' : 'Set up App Store connection',
            'setup',
          );
    return `<p>Apple source: ${esc(source)}</p><p>Inventory: ${esc(data.inventory ? friendly(data.inventory.status) : 'Not read')} · observed ${esc(time(data.inventory?.observed_at))}.</p>${inventoryGuidance(data)}${rows ? `<ul>${rows}</ul>` : '<p>No current report inventory is available.</p>'}<p>Report instance counts describe available files, not downloads, revenue, retention or other metrics. Missing metrics remain unknown.</p>${state}${controls}${impressions}${button('Refresh saved status', 'refresh')}${canRead(data) ? form : ''}${campaignForm(data)}${s?.enabled ? button('Pause refresh', 'pause') : ''}${button('Report / Save PDF', 'report')}<p>Scheduled reads run only while the WMM worker is running. Pausing stops future scheduled reads; it does not remove saved evidence.</p>`;
  }
  function validate(t, data) {
    if (
      !data ||
      data.app_id !== t.scope.app ||
      data.manifest_version !== t.scope.version ||
      data.store_app_id !== t.scope.store ||
      !Array.isArray(data.reports)
    )
      throw Error('App setup changed. Reopen Apple analytics.');
    if (
      data.connection &&
      (!t.scope.bindings.some(
        (b) => b[0] === data.connection.id && b[1] === data.connection.version,
      ) ||
        t.scope.bindings.length !== 1)
    )
      throw Error('Apple connection changed. Refresh this workspace and reopen analytics.');
    return data;
  }
  async function open(d) {
    const initial = scope(d.state);
    if (initial.status !== 'AUTHENTICATED' || !initial.principal) {
      show(
        d,
        'Apple analytics',
        '<p>Sign in with the app owner account to inspect and manage Apple analytics.</p><button type="button" class="button outline" data-action="identity-login">Sign in</button>',
      );
      return;
    }
    if (initial.role !== 'OWNER') {
      show(
        d,
        'Apple analytics',
        '<p>This action requires the current app owner. Ask the owner to review app access, or establish the first owner if this workspace has none.</p>' +
          (d.state.workspace.access?.configured
            ? button('Review app access', 'access')
            : '<button type="button" class="button outline" data-action="access-bootstrap">Establish first owner</button>'),
      );
      return;
    }
    const t = show(d, 'Apple analytics', '<p role="status">Reading saved Apple analytics…</p>');
    try {
      const data = await d.api(
        '/api/apps/' + encodeURIComponent(t.scope.app) + '/apple-analytics/view',
        {},
      );
      if (!current(t)) return;
      validate(t, data);
      show(d, 'Apple analytics', details(data), data);
    } catch (e) {
      if (current(t))
        t.node.querySelector('#apple-analytics-error').textContent =
          e.message + ' Check owner access and App Store setup, then reopen.';
    }
  }
  function busy(t, on) {
    t.pending = on;
    if (current(t)) {
      t.node.setAttribute('aria-busy', String(on));
      t.node.querySelectorAll('button,select,input').forEach((n) => (n.disabled = on));
    }
  }
  function fail(t, e) {
    if (current(t))
      t.node.querySelector('#apple-analytics-error').textContent =
        e.message +
        ' No request was repeated. Check saved Activity and refresh before trying again.';
  }
  function report(data, state, pages) {
    const base = pages.model(state),
      s = data.schedule,
      next = inventoryNextStep(data);
    return {
      ...base,
      title: 'Apple analytics inventory',
      purpose: 'Review saved Apple report availability and refresh settings.',
      cohorts: [],
      metrics: (data.reports || []).map((r) => ({
        label: r.name + ' report instances',
        value: r.instance_count,
        unit: 'instances',
        source: 'Saved Apple inventory',
      })),
      notes: [
        'Inventory observed: ' + (data.inventory?.observed_at || 'Not recorded'),
        'Inventory state: ' + friendly(data.inventory?.status),
        ...(next ? ['Next step: ' + next] : []),
        'Refresh state: ' + friendly(s?.status),
        'Latest job: ' + (s?.last_job || 'Not recorded') + ' · ' + friendly(s?.last_job_status),
        'Consecutive failures: ' + (s?.failures ?? 'Not recorded'),
        'Next due: ' + (s?.enabled ? time(s.next_due, true) : 'Not scheduled'),
        'Last metrics collected: ' + (s?.last_success || 'Not recorded'),
        'Report instance counts are not downloads or other app metrics; unavailable measurements remain unknown.',
      ],
    };
  }
  async function action(node, d) {
    const kind = node.dataset.action;
    if (kind === 'apple-analytics-open') return open(d);
    const t = active;
    if (!t || !current(t) || t.pending) return;
    if (kind === 'apple-analytics-setup') {
      d.close();
      return d.connectionSetup('app_store', t.data?.connection?.id ?? null);
    }
    if (kind === 'apple-analytics-access') {
      d.close();
      return d.openAccess();
    }
    if (kind === 'apple-analytics-job' && t.data?.schedule?.last_job)
      return d.openJob(t.data.schedule.last_job);
    if (kind === 'apple-analytics-refresh') return open(d);
    if (kind === 'apple-analytics-report')
      return d.pageReports.openReport(report(t.data, d.state, d.pageReports), d.browser);
    if (!t.data) return;
    let body, path;
    if (kind === 'apple-analytics-inventory') {
      if (!canRead(t.data)) return;
      path = 'inventory';
      body = {
        manifest_version: t.scope.version,
        connection_id: t.data.connection.id,
        connection_version: t.data.connection.version,
      };
    } else if (kind === 'apple-analytics-impressions') {
      const report = t.data.reports.find(
        (r) =>
          r.name === 'App Store Discovery and Engagement Standard' && r.coverage === 'COMPLETE',
      );
      if (!report || !canRead(t.data)) return;
      path = 'impressions';
      body = { manifest_version: t.scope.version, report_id: report.id };
    } else if (kind === 'apple-analytics-pause') {
      if (!t.data.schedule?.enabled) return;
      path = 'schedule';
      body = {
        manifest_version: t.scope.version,
        enabled: false,
        version: t.data.schedule.version,
      };
    } else return;
    busy(t, true);
    try {
      const result = await d.api(
        '/api/apps/' + encodeURIComponent(t.scope.app) + '/apple-analytics/' + path,
        body,
      );
      if (!current(t)) return;
      if (path === 'inventory' || path === 'impressions') {
        t.node.querySelector('#apple-analytics-status').textContent =
          (path === 'inventory' ? 'Inventory' : 'Store impressions read') +
          ' queued. Check Activity for job ' +
          result.job_id +
          ', then refresh saved status.';
      } else {
        busy(t, false);
        return open(d);
      }
    } catch (e) {
      fail(t, e);
    } finally {
      busy(t, false);
    }
  }
  async function submitCampaign(form, d, mode) {
    const t = active;
    if (!t || !current(t) || t.pending || !form.isConnected || !t.data) return;
    const report = t.data.reports.find((r) => r.name === detailedName && r.coverage === 'COMPLETE');
    const values = new d.FormData(form),
      collecting = mode === 'collect';
    const link = String(values.get('link') || '').trim();
    if (!report || !link || (collecting && (!canRead(t.data) || !t.data.inventory?.job_id))) {
      fail(t, Error('Choose this app’s Apple campaign link and an available Detailed report.'));
      return;
    }
    const body = { manifest_version: t.scope.version, report_id: report.id, link };
    if (collecting) {
      body.inventory_id = t.data.inventory.job_id;
      body.start = values.get('file_start');
      body.end = values.get('file_end');
    } else {
      body.territory = String(values.get('territory') || '')
        .trim()
        .toUpperCase();
      body.start = values.get('start');
      body.end = values.get('end');
    }
    busy(t, true);
    try {
      const path = collecting ? 'campaign-collect-window' : 'campaign-results';
      const result = await d.api(
        '/api/apps/' + encodeURIComponent(t.scope.app) + '/apple-analytics/' + path,
        body,
      );
      if (!current(t)) return;
      if (result.app_id !== t.scope.app) throw Error('App changed. Reopen Apple analytics.');
      if (collecting) {
        const failed = result.jobs.filter((job) =>
          ['FAILED', 'BLOCKED', 'CANCELLED'].includes(job.status),
        ).length;
        t.node.querySelector('#apple-analytics-status').textContent =
          result.jobs.length +
          ' Apple file reads queued or already recorded. Check Activity, then review saved downloads.' +
          (failed
            ? ' Refresh Apple inventory before retrying the ' + failed + ' unsuccessful reads.'
            : '');
      } else {
        t.node.querySelector('#apple-campaign-results').innerHTML = campaignResults(result);
        t.node.querySelector('#apple-analytics-status').textContent =
          'Saved Apple campaign results reviewed.';
      }
    } catch (error) {
      fail(t, error);
    } finally {
      busy(t, false);
    }
  }
  async function submit(form, d, mode) {
    if (form.id === 'apple-campaign-form') return submitCampaign(form, d, mode);
    const t = active;
    if (
      !t ||
      !current(t) ||
      t.pending ||
      !form.isConnected ||
      form.id !== 'apple-analytics-form' ||
      !canRead(t.data)
    )
      return;
    const values = new d.FormData(form),
      reportId = values.get('report_id'),
      hours = Number(values.get('interval_hours'));
    if (
      !Number.isSafeInteger(hours) ||
      hours < 24 ||
      hours > 168 ||
      !t.data.reports.some((r) => r.id === reportId && r.name === 'App Downloads Standard')
    ) {
      fail(t, Error('Choose the displayed downloads report and an interval from 24 to 168 hours.'));
      return;
    }
    const body = {
      manifest_version: t.scope.version,
      enabled: true,
      interval_hours: hours,
      report_id: reportId,
      version: t.data.schedule?.version ?? null,
    };
    busy(t, true);
    try {
      await d.api(
        '/api/apps/' + encodeURIComponent(t.scope.app) + '/apple-analytics/schedule',
        body,
      );
      if (current(t)) {
        busy(t, false);
        return open(d);
      }
    } catch (e) {
      fail(t, e);
    } finally {
      busy(t, false);
    }
  }
  function impressionsResult(result) {
    const data = result.store_impressions,
      sample = Array.isArray(data.sample) ? data.sample : [];
    const rows = sample
      .map(
        (row) =>
          `<tr><td>${esc(row.date)}</td><td>${esc(
            Object.values(row.dimensions || {})
              .filter(Boolean)
              .join(' · ') || 'Unavailable',
          )}</td><td>${esc(row.counts ?? 'Unavailable')}</td><td>${esc(row.unique_counts ?? 'Unavailable')}</td></tr>`,
      )
      .join('');
    return `<h3>App Store impressions</h3><p>Apple counts each report row separately. Unique counts can overlap, so an app-wide total is unavailable here.</p>${rows ? `<p>Showing ${sample.length} of ${esc(data.impression_rows)} impression rows from this read.</p><div class="table-wrap"><table class="result-table"><thead><tr><th scope="col">Date</th><th scope="col">Breakdown</th><th scope="col">Impressions</th><th scope="col">Unique in row</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p>This read returned no current impression rows. Impressions are unknown.</p>'}${data.stale_partitions ? `<p>WMM kept newer saved data for ${esc(data.stale_partitions)} partitions.</p>` : ''}`;
  }
  return {
    panel,
    scope,
    same,
    clear,
    invalidate,
    details,
    report,
    open,
    action,
    submit,
    impressionsResult,
    campaignResults,
  };
});
