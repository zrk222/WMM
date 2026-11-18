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
  const inventoryOption = '@inventory';
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
    const seoBindings = (w.insights?.sources || [])
      .filter((source) => source.provider === 'openseo')
      .map((source) => [source.id, source.version, source.status])
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
      seoBindings,
    };
  }
  const same = (a, b) => a.identityRef === b.identityRef && JSON.stringify(a) === JSON.stringify(b);
  function clear() {
    active = null;
  }
  function invalidate(state) {
    if (!active || same(active.scope, scope(state))) return;
    if (active.performance || active.fetchIntent) {
      active.searchPreview?.close();
      const output = active.node.querySelector('#apple-performance-results');
      if (output) output.innerHTML = '';
      const receipt = active.node.querySelector('#apple-performance-receipt');
      if (receipt) receipt.innerHTML = '';
      const status = active.node.querySelector('#apple-performance-status');
      if (status) status.textContent = 'App access or source setup changed. Reopen the review.';
    }
    clear();
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
    return `<section class="panel" aria-label="Apple analytics"><p class="eyebrow">APP STORE / ANALYTICS</p><h2 id="apple-report-availability-heading" tabindex="-1">Keep Apple analytics current</h2><p>Check report availability and choose whether to refresh the downloads report. Missing report instances do not mean zero downloads.</p>${button('Review Apple analytics', 'open')}</section>`;
  }
  function reviewPanel() {
    return `<section class="panel" aria-labelledby="search-to-store-title"><h2 id="search-to-store-title">Search to App Store</h2><p>Fetch Apple analytics for your dates and review them alongside saved OpenSEO evidence.</p>${button('Open Search to App Store', 'open')}</section>`;
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
    if (value === 'EXPIRED') return 'Check window ended';
    return value ? String(value).replaceAll('_', ' ') : 'Not recorded';
  }
  function localDateTime(date) {
    if (!Number.isFinite(date.getTime())) return '';
    const stamp = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString();
    return stamp
      .slice(0, -1)
      .replace(/\.0+$/, '')
      .replace(/(\.\d*?)0+$/, '$1')
      .replace(/:00$/, '');
  }
  function pendingFirstRead(schedule) {
    const next = Math.round(schedule?.next_due * 1000);
    return schedule?.enabled && !schedule.last_job && next > Date.now()
      ? localDateTime(new Date(next))
      : '';
  }
  function pendingStop(schedule) {
    const stop = Math.round(schedule?.stop_at * 1000);
    return schedule?.enabled && stop > Date.now() ? localDateTime(new Date(stop)) : '';
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
    const statusLabels = {
      READY_TO_REVIEW: 'Ready to review',
      PROVISIONAL: 'Provisional',
      NO_MATCH: 'No matching row',
      NO_FILE: 'No saved file',
    };
    const rows = result.rows
      .map((row) => {
        const status = Object.hasOwn(statusLabels, row.evidence_status)
          ? statusLabels[row.evidence_status]
          : 'Needs review';
        const source = row.source_sha256
          ? `<details><summary>View fingerprint</summary><code>${esc(row.source_sha256)}</code></details>`
          : 'Unavailable';
        return `<tr><th scope="row">${esc(row.date)}</th><td>${esc(row.first_time_downloads ?? 'Unknown')}</td><td>${esc(row.processing_date ?? '—')}</td><td>${esc(status)}</td><td>${source}</td></tr>`;
      })
      .join('');
    return `<h3>Apple-reported first-time downloads · ${esc(result.territory)}</h3><div class="table-wrap"><table class="result-table"><thead><tr><th scope="col">Download date</th><th scope="col">Downloads</th><th scope="col">Apple processed</th><th scope="col">Evidence</th><th scope="col">Source</th></tr></thead><tbody>${rows}</tbody></table></div><p>${esc(result.next_action)}</p>`;
  }
  function performanceForm(data) {
    const end = new Date();
    end.setDate(end.getDate() - 1);
    const start = new Date(end);
    start.setDate(start.getDate() - 4);
    const collect =
      canRead(data) &&
      data.inventory?.coverage === 'COMPLETE' &&
      data.reports.some(
        (r) =>
          ['App Downloads Standard', 'App Store Discovery and Engagement Standard'].includes(
            r.name,
          ) &&
          r.coverage === 'COMPLETE' &&
          r.daily?.length,
      );
    const fetchControl = canRead(data)
      ? '<button type="submit" class="button" value="fetch">Fetch Apple analytics</button>'
      : appleConnectionRepair(data);
    return `<section aria-labelledby="apple-performance-title"><h3 id="apple-performance-title">App Store performance</h3><p>Choose Apple event dates. OpenSEO evidence keeps its own reporting window.</p><form id="apple-performance-form"><div class="field"><label for="apple-performance-start">First event date</label><input id="apple-performance-start" name="start" type="date" value="${localDateTime(start).slice(0, 10)}" required></div><div class="field"><label for="apple-performance-end">Last event date (included)</label><input id="apple-performance-end" name="end" type="date" value="${localDateTime(end).slice(0, 10)}" required></div><div class="toolbar">${fetchControl}<button type="submit" class="button outline" value="search">Review search and App Store results</button>${data.store_app_id ? '<button type="submit" class="button outline" value="fetch-status">Check fetch status</button>' : ''}<button type="submit" class="button outline" value="review">Review saved metrics</button>${collect ? '<button type="submit" class="button outline" value="collect">Collect available Apple files</button>' : ''}</div></form><p id="apple-performance-status" role="status"></p><p id="apple-performance-error" class="field-error" role="alert"></p><div id="apple-performance-receipt"></div><div id="apple-performance-results"></div></section>`;
  }
  function appleConnectionRepair(data) {
    if (!data.store_app_id)
      return '<button type="button" class="button outline" data-action="edit-app">Add App Store ID</button>';
    if (data.connection?.status === 'PROTECTED_STORAGE_UNAVAILABLE')
      return '<p>Unlock protected storage on this host to fetch Apple analytics.</p>';
    return button(
      data.connection ? 'Reconnect App Store Connect' : 'Connect App Store Connect',
      'setup',
    );
  }
  const performanceMetrics = [
    ['App icon list impressions', 'discovery', 'impressions'],
    ['App Store page-view events', 'discovery', 'page_views'],
    ['First-time downloads', 'downloads', 'first_time_downloads'],
    ['Redownloads', 'downloads', 'redownloads'],
  ];
  function performanceValue(row, family, field) {
    const value = row[family].counts[field];
    return value == null
      ? 'Unavailable'
      : String(value) + (row[family].status === 'PROVISIONAL' ? ' (provisional)' : '');
  }
  function hasPerformanceMetrics(result) {
    return result.rows.some((row) =>
      performanceMetrics.some(([, family, field]) => row[family].counts[field] != null),
    );
  }
  function dailyGaps(row) {
    return performanceMetrics.flatMap(([metric, family, field]) => {
      const report = row[family];
      if (report.counts[field] != null) return [];
      return [
        [
          metric,
          report.source_sha256
            ? 'This saved Apple file has no reported count for the metric.'
            : 'No saved Apple report row covers this event date.',
        ],
      ];
    });
  }
  function gapDetails(result) {
    const rows = result.rows
      .map((row) => ({ date: row.date, gaps: dailyGaps(row) }))
      .filter((row) => row.gaps.length);
    return rows.length
      ? `<details><summary>Why daily counts are unavailable</summary>${rows.map((row) => `<h5>${esc(row.date)}</h5>${factsList(row.gaps)}`).join('')}</details>`
      : '';
  }
  function performanceTable(result) {
    if (!hasPerformanceMetrics(result)) {
      const next = result.apple_refresh?.refresh_id
        ? 'Open Apple fetch receipt for the source status.'
        : 'Use Fetch Apple analytics to check and collect Apple files for this date range.';
      return `<p>No Apple metrics are saved for these days. ${next}</p>${gapDetails(result)}`;
    }
    const labels = performanceMetrics.map(([label]) => `<th scope="col">${label}</th>`).join('');
    const rows = result.rows
      .map(
        (row) =>
          `<tr><th scope="row">${esc(row.date)}</th>${performanceMetrics.map(([, family, field]) => `<td>${esc(performanceValue(row, family, field))}</td>`).join('')}</tr>`,
      )
      .join('');
    return `<div class="table-wrap"><table class="result-table"><caption>Daily app-wide counts from Apple’s standard reports</caption><thead><tr><th scope="col">Apple event date</th>${labels}</tr></thead><tbody>${rows}</tbody></table></div>${gapDetails(result)}`;
  }
  function performanceResults(result, ready) {
    const observedOutcome = outcomeRows(result).some((row) => row.value != null);
    return (
      performanceTable(result) +
      outcomeMarkup(result, ready) +
      (hasPerformanceMetrics(result) || observedOutcome
        ? button('Performance report / Save PDF', 'performance-report')
        : '')
    );
  }
  function outcomeRows(result) {
    const coverage = result.outcome_coverage;
    return [...(coverage?.metrics || []), ...(coverage?.cohorts || [])];
  }
  function outcomeFacts(row) {
    return [
      ['Value', row.value ?? 'Unavailable'],
      ['Scope', row.scope],
      ...(row.repair ? [['What to do', row.repair]] : []),
      ...(row.source_sha256 ? [['Source SHA-256', row.source_sha256]] : []),
    ];
  }
  function outcomeMarkup(result, ready) {
    const rows = outcomeRows(result);
    if (!rows.length) return '';
    return `<section aria-labelledby="apple-outcome-coverage"><h4 id="apple-outcome-coverage">Other Apple metrics and coverage</h4>${rows.map((row) => `<details${row.repair ? ' open' : ''}><summary>${esc(row.label)} <strong>${esc(row.value ?? 'Unavailable')}</strong></summary>${factsList(outcomeFacts(row).slice(1))}${ready && row.campaign_report_id ? button('Fetch campaign downloads', 'campaign-fetch', `data-id="${esc(row.campaign_report_id)}"`) : ''}</details>`).join('')}</section>`;
  }
  function searchReview(result) {
    const review = result.search_review;
    const fields = [
      'insight',
      'next_action',
      'success_metric',
      'guardrail',
      'follow_up',
      'web_source',
      'evidence_status',
    ];
    if (
      !review ||
      !fields.every((key) => typeof review[key] === 'string') ||
      !Array.isArray(review.web_facts) ||
      !review.web_facts.every((fact) => typeof fact === 'string') ||
      !Array.isArray(review.actions) ||
      !review.actions.every(
        (action) =>
          ['id', 'title', 'task', 'metric', 'guardrail', 'follow_up', 'agent'].every(
            (key) => typeof action?.[key] === 'string',
          ) &&
          Array.isArray(action.depends_on) &&
          action.depends_on.every((id) => typeof id === 'string'),
      )
    )
      throw Error('The saved search review could not be read. Review the selected dates again.');
    return review;
  }
  function reviewFacts(review) {
    return [
      ['Recommended action', review.next_action],
      ['Measure', review.success_metric],
      ['Keep fixed', review.guardrail],
      ['Review again', review.follow_up],
    ];
  }
  function timing(action, actions) {
    return action.depends_on.length
      ? 'After ' +
          action.depends_on
            .map((id) => actions.find((item) => item.id === id)?.title || id)
            .join(', ')
      : 'Can run in parallel';
  }
  function actionFacts(action, actions) {
    return [
      ['Task', action.task],
      ['Measure', action.metric],
      ['Keep fixed', action.guardrail],
      ['Review again', action.follow_up],
      ['Suggested role', action.agent],
      ['Timing', timing(action, actions)],
    ];
  }
  function factsList(facts) {
    return `<dl class="details-list">${facts.map(([label, value]) => `<div class="detail-item"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>`;
  }
  function savedAction(review, id) {
    return review.saved_actions?.find(
      (receipt) => receipt.action_id === id && receipt.status === 'SAVED',
    );
  }
  function assignment(review, id) {
    return Object.hasOwn(review.assignments || {}, id) ? review.assignments[id] : null;
  }
  function assignmentFacts(job) {
    if (!job) return [];
    const status = {
      ASSIGNED: 'Awaiting agent',
      COMPLETED: 'Completed',
      NEEDS_EXTERNAL_VERIFICATION: 'Needs external verification',
    };
    return [
      ['Assigned agent', job.agent_id],
      ['Agent status', status[job.status] || 'Check plan status'],
      ...(job.receipt_sha256 ? [['Execution receipt SHA-256', job.receipt_sha256]] : []),
      ...(job.deliverable
        ? [
            ['Agent deliverable', job.deliverable.summary],
            ['Deliverable details', JSON.stringify(job.deliverable.details)],
          ]
        : []),
    ];
  }
  function assignmentMarkup(action, review, selector) {
    const job = assignment(review, action.id);
    if (job) return factsList(assignmentFacts(job));
    const agents = review.team_agents || [];
    if (!review.review_hash || !agents.length) return '';
    const choices = agents
      .map((agent) => `<option value="${esc(agent.grant_id)}">${esc(agent.agent_id)}</option>`)
      .join('');
    return `<label class="field">Agent for ${esc(action.title)}<select data-search-agent="${esc(action.id)}"><option value="">Choose an eligible agent</option>${choices}</select></label>${button('Assign to agent', 'search-assign', selector)}`;
  }
  function searchActionMarkup(action, review) {
    const selector = `data-id="${esc(action.id)}"`;
    const saved = savedAction(review, action.id);
    const canSave = typeof review.review_hash === 'string' && review.review_hash.length;
    const sourceControl =
      action.id === 'web-baseline'
        ? button('Review OpenSEO source', 'search-openseo')
        : ['apple-baseline', 'measure-tag'].includes(action.id)
          ? button('Open Apple report controls', 'search-apple')
          : '';
    return `<details data-search-draft="${esc(action.id)}"><summary>${esc(action.title)}</summary>${factsList(actionFacts(action, review.actions))}${saved ? '<p>Draft saved in WMM.</p>' : canSave ? button('Save action', 'search-save', selector) : ''}${button('Download draft', 'search-download-draft', selector)}${sourceControl}${assignmentMarkup(action, review, selector)}</details>`;
  }
  function assignmentProgress(review) {
    const assigned = review.actions.map((action) => assignment(review, action.id)).filter(Boolean);
    if (!assigned.length) return '';
    const completed = assigned.filter((job) => job.status === 'COMPLETED').length;
    const verify = assigned.filter((job) => job.status === 'NEEDS_EXTERNAL_VERIFICATION').length;
    return `<p>${assigned.length} of ${review.actions.length} steps assigned. ${completed} completed.${verify ? ' Steps needing external verification: ' + verify + '.' : ''}</p>`;
  }
  function earlierReceipts(review) {
    return (review.earlier_plans || []).flatMap((plan) =>
      plan.saved_actions.map((receipt) => ({
        title: receipt.action.title,
        status: 'Earlier plan',
        facts: [
          ['Saved on', receipt.created],
          ['WMM draft receipt', receipt.id],
          ['Earlier review SHA-256', plan.review_hash],
          ...assignmentFacts(assignment(plan, receipt.action_id)),
        ],
      })),
    );
  }
  function earlierMarkup(review) {
    const items = earlierReceipts(review);
    if (!items.length) return '';
    return `<details data-search-history><summary>Earlier plan receipts for these dates (${items.length})</summary>${items.map((item) => `<h5>${esc(item.title)}</h5>${factsList(item.facts)}`).join('')}</details>`;
  }
  function webSources(t) {
    return (t.d.state.workspace.insights?.sources || []).filter(
      (item) =>
        item.provider === 'openseo' && !['DISCONNECTED', 'CLEANUP_REQUIRED'].includes(item.status),
    );
  }

  function webFetchControl(sources) {
    if (!sources.length) return '';
    const picker =
      sources.length > 1
        ? `<label class="field">OpenSEO project<select data-search-web-source required><option value="">Choose a project</option>${sources.map((s) => `<option value="${esc(s.id)}">${esc(s.data?.project_id || s.id)} · ${esc(s.data?.territory || '')}</option>`).join('')}</select></label>`
        : '';
    return picker + button('Fetch OpenSEO search data', 'search-fetch-web');
  }

  async function fetchWeb(t, d) {
    const sources = webSources(t);
    const source =
      sources.length === 1
        ? sources[0]
        : sources.find(
            (item) => item.id === t.node.querySelector('[data-search-web-source]')?.value,
          );
    if (!source) throw Error('Choose a connected OpenSEO project for this app.');
    const base =
      '/api/apps/' + encodeURIComponent(t.scope.app) + '/insights/' + encodeURIComponent(source.id);
    const read = await d.api(base + '/web-read', { confirm_read: true });
    if (!current(t)) return;
    if (!read.report_id || read.status !== 'CONNECTED')
      throw Error(
        read.error || 'OpenSEO could not complete the read. Inspect the project connection.',
      );
    if (!read.report?.web_evidence)
      throw Error(
        'OpenSEO returned no eligible app-page rows. Review the property, market and coverage in source setup.',
      );
    await d.api(base + '/save-web-evidence', {
      id: d.uuid(),
      manifest_version: t.scope.version,
      report_id: read.report_id,
    });
  }

  function searchResults(result, sources, ready) {
    const review = result.search_review;
    const team = review.team_agents?.length
      ? '<p>Assign actions to eligible agents. A step waits for its prerequisites and for its assigned agent to run it through WMM.</p>'
      : `<p>Agent assignments require an eligible WMM agent grant.</p>${button('Open agent access', 'search-agents')}`;
    return `<section aria-labelledby="apple-search-review-title"><h3 id="apple-search-review-title">Search to App Store</h3><p><strong>${esc(review.evidence_status)}</strong></p><p>${esc(review.insight)}</p>${factsList(reviewFacts(review))}<h4>OpenSEO evidence</h4><p>${esc(review.web_source)}</p>${webFetchControl(sources)}${review.web_facts.length ? `<ul>${review.web_facts.map((fact) => `<li>${esc(fact)}</li>`).join('')}</ul>` : ''}<h4>Apple evidence</h4><p>Apple event dates ${esc(result.start)} to ${esc(result.end)}.</p>${performanceTable(result)}${outcomeMarkup(result, ready)}<h4>Proposed work</h4><p>Saving an action keeps a draft for this app.</p>${team}${assignmentProgress(review)}${review.actions.map((action) => searchActionMarkup(action, review)).join('')}${earlierMarkup(review)}<div class="toolbar">${button('Search to App Store report / Save PDF', 'search-report')}${button('Download action plan', 'search-download')}${button('Refresh plan status', 'search-refresh')}</div></section>`;
  }
  function planScope(result) {
    return {
      app_id: result.app_id,
      store_app_id: result.store_app_id,
      start: result.start,
      end: result.end,
      review_hash: result.search_review.review_hash ?? null,
    };
  }
  function planExport(result) {
    const review = result.search_review;
    const rows = result.rows.map((row) => ({
      date: row.date,
      ...Object.fromEntries(
        ['discovery', 'downloads'].map((family) => {
          const { counts, status, processing_date, source_sha256 } = row[family];
          const selected = performanceMetrics
            .filter(([, type]) => type === family)
            .map(([, , field]) => [field, counts[field]]);
          return [
            family,
            { counts: Object.fromEntries(selected), status, processing_date, source_sha256 },
          ];
        }),
      ),
    }));
    const {
      insight,
      next_action,
      success_metric,
      guardrail,
      follow_up,
      web_source,
      evidence_status,
      web_facts,
      web_evidence_sha256,
      actions,
      saved_actions,
      assignments,
    } = review;
    return {
      ...planScope(result),
      search_review: {
        insight,
        next_action,
        success_metric,
        guardrail,
        follow_up,
        web_source,
        evidence_status,
        web_facts,
        web_evidence_sha256,
        actions,
        saved_actions,
        assignments,
        earlier_plans: review.earlier_plans || [],
      },
      rows,
      outcome_coverage: result.outcome_coverage,
      apple_refresh: result.apple_refresh,
    };
  }
  function renderSearch(t, result) {
    const output = t.node.querySelector('#apple-performance-results');
    if (sameFetchWindow(t.fetchReceipt, result) && t.fetchReceipt.refresh_id)
      result.apple_refresh = t.fetchReceipt;
    const expanded = new Set(
      Array.from(
        output.querySelectorAll('[data-search-draft][open]'),
        (item) => item.dataset.searchDraft,
      ),
    );
    const agents = new Map(
      Array.from(output.querySelectorAll('[data-search-agent]'), (item) => [
        item.dataset.searchAgent,
        item.value,
      ]),
    );
    output.innerHTML = searchResults(result, webSources(t), canRead(t.data));
    output.querySelectorAll('[data-search-draft]').forEach((item) => {
      item.open = expanded.has(item.dataset.searchDraft);
    });
    output.querySelectorAll('[data-search-agent]').forEach((item) => {
      const previous = agents.get(item.dataset.searchAgent);
      if (previous && Array.from(item.options).some((option) => option.value === previous))
        item.value = previous;
    });
  }
  function validatePerformance(t, result, body) {
    if (
      result.app_id !== t.scope.app ||
      result.store_app_id !== t.scope.store ||
      result.start !== body.start ||
      result.end !== body.end ||
      !Array.isArray(result.rows)
    )
      throw Error('Apple report dates or app changed. Review the selected dates again.');
  }
  function searchBody(t) {
    return {
      manifest_version: t.scope.version,
      start: t.performance.start,
      end: t.performance.end,
    };
  }
  function searchPath(t, operation) {
    return '/api/apps/' + encodeURIComponent(t.scope.app) + '/apple-analytics/' + operation;
  }
  async function searchAction(kind, t, d, node) {
    const result = t.performance;
    const action = result.search_review.actions.find((item) => item.id === node.dataset.id);
    if (kind === 'search-report') {
      t.searchPreview = d.pageReports.openReport(
        searchReport(result, d.state, d.pageReports),
        d.browser,
        node,
      );
      return t.searchPreview;
    }
    if (kind === 'search-download')
      return d.download('search-to-app-store-plan.json', planExport(result));
    if (kind === 'search-download-draft' && action)
      return d.download('search-to-app-store-' + action.id + '.json', {
        ...planScope(result),
        action,
        source: result.search_review.web_source,
        web_evidence_sha256: result.search_review.web_evidence_sha256 ?? null,
        draft_receipt: savedAction(result.search_review, action.id) ?? null,
        assignment: assignment(result.search_review, action.id),
      });
    if (kind === 'search-openseo') {
      d.close();
      return d.openOpenSEO();
    }
    if (kind === 'search-agents') {
      d.close();
      return d.openAgents();
    }
    if (kind === 'search-apple') {
      const inventory = t.node.querySelector('[data-action="apple-analytics-inventory"]');
      const setup = t.node.querySelector('[data-action="apple-analytics-setup"]');
      return (inventory || setup || t.node.querySelector('#apple-performance-start'))?.focus();
    }
    if (!['search-save', 'search-assign', 'search-refresh', 'search-fetch-web'].includes(kind))
      return;
    const review = result.search_review;
    const assigns = kind === 'search-assign';
    const fetchWebSource = kind === 'search-fetch-web';
    const changes = kind === 'search-save' || assigns;
    if (changes && (!action || !review.review_hash)) return;
    const status = t.node.querySelector('#apple-performance-status');
    const message = t.node.querySelector('#apple-performance-error');
    status.textContent = '';
    message.textContent = '';
    const grant = assigns
      ? Array.from(t.node.querySelectorAll('[data-search-agent]')).find(
          (item) => item.dataset.searchAgent === action.id,
        )?.value
      : null;
    if (assigns && !review.team_agents?.some((item) => item.grant_id === grant)) {
      message.textContent = 'Choose an eligible agent for this step.';
      return;
    }
    const body = searchBody(t);
    busy(t, true);
    try {
      if (fetchWebSource) {
        status.textContent = 'Fetching the connected OpenSEO project…';
        await fetchWeb(t, d);
        if (!current(t)) return;
      }
      if (changes) {
        const response = await d.api(
          searchPath(t, assigns ? 'search-review-assign' : 'search-review-save'),
          {
            ...body,
            review_hash: review.review_hash,
            action_id: action.id,
            ...(assigns ? { grant_id: grant } : {}),
          },
        );
        if (!current(t)) return;
        if (
          response.app_id !== t.scope.app ||
          response.review_hash !== review.review_hash ||
          response.receipt?.action_id !== action.id ||
          response.receipt?.status !== 'SAVED'
        )
          throw Error('The saved draft receipt could not be verified.');
        review.saved_actions = [
          ...(review.saved_actions || []).filter((item) => item.action_id !== action.id),
          response.receipt,
        ];
        if (!assigns) status.textContent = 'Draft saved in WMM.';
      }
      if (assigns || !changes) {
        const refreshed = await d.api(searchPath(t, 'search-review'), body);
        if (!current(t)) return;
        validatePerformance(t, refreshed, body);
        searchReview(refreshed);
        t.performance = refreshed;
        const job = assigns ? assignment(refreshed.search_review, action.id) : null;
        status.textContent = assigns
          ? job?.grant_id === grant
            ? 'Step assigned to ' + job.agent_id + '.'
            : 'Plan refreshed. Review the current assignment before retrying.'
          : fetchWebSource
            ? 'OpenSEO data fetched and saved. The review now uses the new reading.'
            : 'Search to App Store plan refreshed.';
      }
      renderSearch(t, t.performance);
      if (action) {
        const drafts = Array.from(t.node.querySelectorAll('[data-search-draft]'));
        drafts
          .find((item) => item.dataset.searchDraft === action.id)
          ?.querySelector('summary')
          ?.focus();
      } else t.node.querySelector('[data-action="apple-analytics-search-refresh"]')?.focus();
    } catch (error) {
      if (current(t))
        message.textContent =
          error.message + (assigns ? ' Refresh plan status before trying again.' : '');
    } finally {
      busy(t, false);
    }
  }
  function searchReport(result, state, pages) {
    const base = performanceReport(result, state, pages);
    const review = result.search_review;
    const earlier = earlierReceipts(review);
    const facts = (action) => {
      const receipt = savedAction(review, action.id);
      return [
        ...actionFacts(action, review.actions),
        ...(receipt ? [['WMM draft receipt', receipt.id]] : []),
        ...assignmentFacts(assignment(review, action.id)),
      ];
    };
    return {
      ...base,
      title: 'Search to App Store',
      purpose: review.insight,
      next_step: review.next_action,
      sections: [
        {
          title: 'Decision',
          items: [
            {
              title: 'Next acquisition decision',
              status: review.evidence_status,
              facts: reviewFacts(review),
            },
          ],
        },
        {
          title: 'OpenSEO evidence',
          items: [
            {
              title: review.web_source,
              status: 'Independent reporting window',
              facts: [
                ...review.web_facts.map((fact) => ['Evidence', fact]),
                ...(review.web_evidence_sha256
                  ? [['OpenSEO source SHA-256', review.web_evidence_sha256]]
                  : []),
              ],
            },
          ],
        },
        ...base.sections,
        {
          title: 'Proposed work',
          items: review.actions.map((action) => ({
            title: action.title,
            status: savedAction(review, action.id) ? 'Draft saved' : 'Proposed',
            facts: facts(action),
          })),
        },
        ...(earlier.length
          ? [{ title: 'Earlier plan receipts for these dates', items: earlier }]
          : []),
      ],
      notes: [
        ...base.notes,
        'OpenSEO figures describe web search. Apple figures describe App Store events. The report keeps each source’s scope and reporting window.',
      ],
    };
  }
  function performanceReport(result, state, pages) {
    const outcomes = outcomeRows(result);
    return {
      ...pages.appReportModel(state),
      title: 'App Store performance',
      purpose: 'App-wide daily event counts from saved Apple standard reports.',
      next_step: 'Fetch Apple analytics for the selected dates to check for newer files.',
      filters: {
        apple_app_id: result.store_app_id,
        first_event_date: result.start,
        last_event_date: result.end,
      },
      sections: [
        ...(result.apple_refresh?.refresh_id
          ? [
              {
                title: 'Apple fetch receipt',
                items: [
                  {
                    title: 'Refresh attempt',
                    status: fetchLabel(result.apple_refresh.status),
                    facts: fetchFacts(result.apple_refresh),
                  },
                  ...result.apple_refresh.files.map((file) => ({
                    title: file.report_family,
                    status: friendly(file.status),
                    facts: [
                      ['Processing date', file.processing_date],
                      ['Worker job', file.job_id],
                      ...(file.observed_at
                        ? [['Apple file observed', time(file.observed_at)]]
                        : []),
                    ],
                  })),
                ],
              },
            ]
          : []),
        {
          title: 'Daily App Store results',
          items: result.rows.map((row) => ({
            title: row.date,
            status: Object.values({ discovery: row.discovery, downloads: row.downloads }).some(
              (source) => source.source_sha256,
            )
              ? 'Apple report saved'
              : 'Unavailable',
            facts: [
              ...performanceMetrics.map(([label, family, field]) => [
                label,
                performanceValue(row, family, field),
              ]),
              ...dailyGaps(row).map(([metric, reason]) => [metric + ' coverage', reason]),
              ...[
                ['Discovery', row.discovery],
                ['Downloads', row.downloads],
              ].flatMap(([label, source]) =>
                source.source_sha256
                  ? [
                      [label + ' processed', source.processing_date],
                      [label + ' source SHA-256', source.source_sha256],
                    ]
                  : [],
              ),
            ],
          })),
        },
        ...(outcomes.length
          ? [
              {
                title: 'Other Apple metrics and coverage',
                items: outcomes.map((row) => ({
                  title: row.label,
                  status: row.value == null ? 'Unavailable' : 'Observed',
                  facts: outcomeFacts(row),
                })),
              },
            ]
          : []),
      ],
      notes: [
        'Counts come from the latest collected daily Apple file for each event date and report family. Figures count events. Unique audience counts stay at Apple’s report-row level.',
        'List impressions cover app icons shown in a list. Page-view events can include app and in-app event pages. App Store Connect dashboard figures use separate metric definitions.',
        'Missing or suppressed values are unavailable. Apple can issue corrections after the normal reporting delay.',
      ],
    };
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
    const nextCheck =
      s?.enabled && (!s.stop_at || s.next_due < s.stop_at)
        ? time(s.next_due, true)
        : 'Not scheduled';
    const deadline = s?.stop_at ? `<br>Stop time: ${esc(time(s.stop_at, true))}` : '';
    const refreshState =
      s?.status === 'EXPIRED'
        ? '<span class="status expired">Check window ended</span>'
        : esc(friendly(s?.status));
    const state = s
      ? `<p><strong>Refresh:</strong> ${refreshState} · ${s.enabled ? 'On' : 'Off'}${s.mode === 'inventory' ? ' · Report availability' : ''}<br>Last job: ${esc(s.last_job || 'Not recorded')} · ${esc(s.last_job_status ? friendly(s.last_job_status) : 'No status')} · Failures: ${esc(s.failures)}<br>Last metrics collected: ${esc(time(s.last_success))} · Next due: ${esc(nextCheck)}${deadline}</p>${['BLOCKED', 'FAILED'].includes(s.last_job_status) ? '<p>Inspect the latest refresh and repair the reported issue before trying again.</p>' : ''}${s.last_job ? button('Inspect latest refresh', 'job') : ''}`
      : '<p>No saved refresh schedule.</p>';
    const rows = reports
      .map(
        (r) =>
          `<li>${esc(r.name)}: ${esc(r.instance_count)} report instances · ${esc(friendly(r.coverage))}</li>`,
      )
      .join('');
    const selects = [
      ...options.map(
        (r) =>
          `<option value="${esc(r.id)}" ${s?.report_id === r.id ? 'selected' : ''}>${esc(r.name)}</option>`,
      ),
      `<option value="${inventoryOption}" ${s?.mode === 'inventory' ? 'selected' : ''}>Report availability</option>`,
    ].join('');
    const form = `<form id="apple-analytics-form"><div class="field"><label for="apple-analytics-report">What should WMM check?</label><select id="apple-analytics-report" name="report_id" aria-describedby="apple-refresh-purpose" required>${selects}</select></div><p id="apple-refresh-purpose">Report availability checks whether Apple has files for this app. It does not collect download counts.</p><div class="field"><label for="apple-analytics-interval">Refresh every (hours)</label><input id="apple-analytics-interval" type="number" name="interval_hours" min="24" max="168" step="1" value="${esc(s?.interval_hours || 24)}" required></div><div class="field"><label for="apple-analytics-first-read">First check time (optional)</label><input id="apple-analytics-first-read" type="datetime-local" step="any" name="first_read_at" aria-describedby="apple-first-read-help" value="${esc(pendingFirstRead(s))}"><p id="apple-first-read-help">Use your device time zone. Choose a time within seven days, or leave blank to start when WMM is ready.</p></div>
<div class="field"><label for="apple-analytics-stop">Stop checking at (optional)</label><input id="apple-analytics-stop" type="datetime-local" step="any" name="stop_at" aria-describedby="apple-stop-help" value="${esc(pendingStop(s))}"><p id="apple-stop-help">Choose a local time after the first check and within seven days. Leave blank to keep checking until you pause.</p></div>
<button class="button" type="submit">${s?.enabled ? 'Save refresh settings' : 'Enable refresh'}</button></form>`;
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
    return `${performanceForm(data)}<p>Apple source: ${esc(source)}</p><p>Inventory: ${esc(data.inventory ? friendly(data.inventory.status) : 'Not read')} · observed ${esc(time(data.inventory?.observed_at))}.</p>${inventoryGuidance(data)}${rows ? `<ul>${rows}</ul>` : '<p>No current report inventory is available.</p>'}<p>Report instance counts describe available files, not downloads, revenue, retention or other metrics. Missing metrics remain unknown.</p>${state}${controls}${impressions}${button('Refresh saved status', 'refresh')}${canRead(data) ? form : ''}${campaignForm(data)}${s?.enabled ? button('Pause refresh', 'pause') : ''}${button('Inventory report / Save PDF', 'report')}<p>Scheduled reads run only while the WMM worker is running. Pausing stops future scheduled reads; it does not remove saved evidence.</p>`;
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
        '<p>Sign in with the app owner account. WMM will return here so you can choose whether to read Apple reports.</p><button type="button" class="button outline" data-action="identity-login" data-id="apple-analytics">Sign in</button>',
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
    if (
      kind === 'apple-analytics-campaign-fetch' &&
      t.performance &&
      node.dataset.id &&
      outcomeRows(t.performance).some((row) => row.campaign_report_id === node.dataset.id)
    )
      return fetchApple(t, d, searchBody(t), true, node.dataset.id);
    if (kind.startsWith('apple-analytics-search-') && t.performance?.search_review)
      return searchAction(kind.slice('apple-analytics-'.length), t, d, node);
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
    if (kind === 'apple-analytics-performance-report' && t.performance)
      return d.pageReports.openReport(
        performanceReport(t.performance, d.state, d.pageReports),
        d.browser,
        node,
      );
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
  const inProgress = (status) => status === 'INVENTORY' || status === 'COLLECTING';
  const fetchLabels = {
    NOT_REQUESTED: 'No Apple fetch recorded',
    INVENTORY: 'Checking Apple report availability',
    COLLECTING: 'Collecting Apple files',
    READY: 'Apple file collection finished',
    INCOMPLETE: 'Some Apple files need review',
    FAILED: 'Apple fetch needs attention',
    SOURCE_CHANGED: 'Apple source changed',
    WAITING_FOR_REPORTS: 'Waiting for Apple report files',
    REPORT_SETUP_REQUIRED: 'Apple report setup required',
    REQUEST_INVENTORY_PARTIAL: 'Apple inventory is incomplete',
    NO_FILES_FOR_DATES: 'No Apple files for these dates',
  };
  const fetchLabel = (status) => fetchLabels[status] || 'Check Apple fetch status';
  function fetchFacts(receipt) {
    return [
      ['Apple event dates', receipt.start + ' to ' + receipt.end],
      ['Refresh ID', receipt.refresh_id],
      ...(receipt.requested_at ? [['Request recorded', time(receipt.requested_at)]] : []),
      ['Inventory job', receipt.inventory_job_id ?? 'Unavailable'],
      ['Inventory status', friendly(receipt.inventory_status)],
      ...(receipt.inventory_observed_at
        ? [['Apple inventory observed', time(receipt.inventory_observed_at)]]
        : []),
      ['Apple report state', friendly(receipt.provider_status)],
      ['File coverage', friendly(receipt.coverage)],
      ...(receipt.reason ? [['Source detail', receipt.reason]] : []),
    ];
  }
  function showFetch(t, receipt, status) {
    const count = receipt.files.length;
    const finished = receipt.files.filter(
      (job) => !['QUEUED', 'RUNNING'].includes(job.status),
    ).length;
    status.textContent =
      fetchLabel(receipt.status) +
      ' · ' +
      receipt.start +
      ' to ' +
      receipt.end +
      (receipt.inventory_observed_at
        ? ' · Apple inventory observed ' + time(receipt.inventory_observed_at)
        : '') +
      (count ? ' · ' + finished + ' of ' + count + ' file reads finished' : '') +
      (receipt.reason ? '. ' + receipt.reason : '.');
    const output = t.node.querySelector('#apple-performance-receipt');
    if (output)
      output.innerHTML = receipt.refresh_id
        ? `<details><summary>Apple fetch receipt</summary>${factsList(fetchFacts(receipt))}${receipt.files.length ? `<ul>${receipt.files.map((file) => `<li>${esc(file.report_family)} · ${esc(file.processing_date)} · ${esc(friendly(file.status))}${file.observed_at ? ` · observed ${esc(time(file.observed_at))}` : ''}<br><code>${esc(file.job_id)}</code></li>`).join('')}</ul>` : ''}</details>`
        : '';
    t.fetchReceipt = receipt;
  }
  function checkFetchReceipt(t, receipt, body) {
    if (
      !receipt ||
      receipt.app_id !== t.scope.app ||
      receipt.store_app_id !== t.scope.store ||
      receipt.start !== body.start ||
      receipt.end !== body.end ||
      !Object.hasOwn(fetchLabels, receipt.status) ||
      !Array.isArray(receipt.files)
    )
      throw Error('Apple receipt does not match the selected dates and app.');
    return {
      app_id: receipt.app_id,
      store_app_id: receipt.store_app_id,
      start: receipt.start,
      end: receipt.end,
      status: receipt.status,
      refresh_id: receipt.refresh_id,
      requested_at: receipt.requested_at,
      inventory_job_id: receipt.inventory_job_id,
      inventory_status: receipt.inventory_status,
      inventory_observed_at: receipt.inventory_observed_at,
      provider_status: receipt.provider_status,
      coverage: receipt.coverage,
      reason: receipt.reason,
      files: receipt.files.map(
        ({ job_id, status, processing_date, report_family, observed_at }) => ({
          job_id,
          status,
          processing_date,
          report_family,
          observed_at,
        }),
      ),
    };
  }
  const sameFetchWindow = (receipt, selection) =>
    Boolean(receipt && receipt.start === selection.start && receipt.end === selection.end);
  function clearOldWindow(t, selection) {
    if (sameFetchWindow(t.performance, selection)) return;
    t.performance = null;
    const results = t.node.querySelector('#apple-performance-results');
    if (results) results.innerHTML = '';
    const receipt = t.node.querySelector('#apple-performance-receipt');
    if (receipt) receipt.innerHTML = '';
  }
  function fetchIntent(t, d, body, campaignReport) {
    const connection = t.data.connection;
    const scope = JSON.stringify([
      body.start,
      body.end,
      connection.id,
      connection.version,
      campaignReport,
    ]);
    if (t.fetchIntent?.scope !== scope) t.fetchIntent = { scope, request_id: d.uuid() };
    return {
      ...body,
      connection_id: connection.id,
      connection_version: connection.version,
      request_id: t.fetchIntent.request_id,
      ...(campaignReport ? { campaign_report_id: campaignReport } : {}),
    };
  }
  async function fetchApple(t, d, body, start, campaignReport = null) {
    const status = t.node.querySelector('#apple-performance-status');
    const message = t.node.querySelector('#apple-performance-error');
    const resume = sameFetchWindow(t.fetchReceipt, body) && inProgress(t.fetchReceipt.status);
    start = start && !resume;
    if (start && !canRead(t.data)) return;
    if (!t.scope.store) return;
    clearOldWindow(t, body);
    status.textContent = start
      ? 'Requesting Apple analytics for the selected dates…'
      : 'Reading saved Apple fetch status…';
    message.textContent = '';
    busy(t, true);
    try {
      const initial = start
        ? await d.api(
            searchPath(t, campaignReport ? 'campaign-refresh' : 'performance-refresh'),
            fetchIntent(t, d, body, campaignReport),
          )
        : await d.api(searchPath(t, 'performance-refresh-status'), body);
      if (!current(t)) return;
      let receipt = checkFetchReceipt(t, initial, body);
      const refreshId = receipt.refresh_id;
      showFetch(t, receipt, status);
      for (let attempt = 0; inProgress(receipt.status) && attempt < 10; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, attempt ? 3000 : 1000));
        if (!current(t)) return;
        const update = await d.api(searchPath(t, 'performance-refresh-status'), body);
        if (!current(t)) return;
        receipt = checkFetchReceipt(t, update, body);
        if (receipt.refresh_id !== refreshId)
          throw Error(
            'Another fetch is current for these dates. Use Check fetch status to inspect it.',
          );
        showFetch(t, receipt, status);
      }
      if (inProgress(receipt.status)) {
        status.textContent +=
          ' The worker continues. Use Check fetch status to see the latest receipt.';
        return;
      }
      t.fetchIntent = null;
      if (receipt.status === 'SOURCE_CHANGED') {
        t.performance = null;
        t.node.querySelector('#apple-performance-results').innerHTML = '';
        return;
      }
      const result = await d.api(searchPath(t, 'search-review'), body);
      if (!current(t)) return;
      validatePerformance(t, result, body);
      searchReview(result);
      t.performance = { ...result, apple_refresh: receipt };
      renderSearch(t, t.performance);
    } catch (error) {
      if (current(t)) {
        if (!sameFetchWindow(t.fetchReceipt, body))
          status.textContent = 'Apple fetch status was not confirmed.';
        message.textContent =
          error.message + ' Use Check fetch status to inspect the saved attempt.';
      }
    } finally {
      busy(t, false);
    }
  }
  async function submitPerformance(form, d, mode) {
    const t = active;
    if (!t || !current(t) || t.pending || !form.isConnected || !t.data) return;
    mode ??= canRead(t.data) ? 'fetch' : 'search';
    const values = new d.FormData(form);
    const body = {
      manifest_version: t.scope.version,
      start: values.get('start'),
      end: values.get('end'),
    };
    if (mode === 'fetch' || mode === 'fetch-status')
      return fetchApple(t, d, body, mode === 'fetch');
    clearOldWindow(t, body);
    const collecting = mode === 'collect';
    const search = mode === 'search';
    if (collecting) {
      if (!canRead(t.data) || !t.data.inventory?.job_id) return;
      body.inventory_id = t.data.inventory.job_id;
    }
    const status = t.node.querySelector('#apple-performance-status');
    const message = t.node.querySelector('#apple-performance-error');
    status.textContent = '';
    message.textContent = '';
    busy(t, true);
    try {
      const result = await d.api(
        searchPath(
          t,
          collecting ? 'performance-collect' : search ? 'search-review' : 'performance',
        ),
        body,
      );
      if (!current(t)) return;
      if (result.app_id !== t.scope.app) throw Error('App changed. Reopen Apple analytics.');
      if (collecting) {
        const failed = result.jobs.filter((job) =>
          ['FAILED', 'BLOCKED', 'CANCELLED'].includes(job.status),
        ).length;
        status.textContent =
          result.jobs.length +
          ' Apple file reads queued or already recorded. Check Activity, then review saved metrics.' +
          (failed ? ' Refresh Apple inventory before retrying unsuccessful reads.' : '');
      } else {
        validatePerformance(t, result, body);
        if (search) searchReview(result);
        t.performance = result;
        if (sameFetchWindow(t.fetchReceipt, body) && t.fetchReceipt.refresh_id)
          result.apple_refresh = t.fetchReceipt;
        if (search) renderSearch(t, result);
        else
          t.node.querySelector('#apple-performance-results').innerHTML = performanceResults(
            result,
            canRead(t.data),
          );
        status.textContent = search
          ? 'Search and App Store results reviewed.'
          : 'Saved App Store metrics reviewed.';
      }
    } catch (error) {
      if (current(t)) message.textContent = error.message;
    } finally {
      busy(t, false);
    }
  }
  async function submit(form, d, mode) {
    if (form.id === 'apple-campaign-form') return submitCampaign(form, d, mode);
    if (form.id === 'apple-performance-form') return submitPerformance(form, d, mode);
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
      (reportId !== inventoryOption &&
        !t.data.reports.some((r) => r.id === reportId && r.name === 'App Downloads Standard'))
    ) {
      fail(
        t,
        Error(
          'Choose report availability or a downloads report, and an interval from 24 to 168 hours.',
        ),
      );
      return;
    }
    const chosen = values.get('first_read_at');
    const firstRead = chosen ? new Date(String(chosen)) : null;
    const now = Date.now();
    if (
      firstRead &&
      (localDateTime(firstRead) !== chosen ||
        firstRead.getTime() < now ||
        firstRead.getTime() > now + 7 * 86400000)
    ) {
      fail(t, Error('Choose a first Apple check within the next seven days.'));
      return;
    }
    const stopChosen = values.get('stop_at');
    const stop = stopChosen ? new Date(String(stopChosen)) : null;
    if (
      stop &&
      (localDateTime(stop) !== stopChosen ||
        stop.getTime() <= (firstRead?.getTime() ?? now) ||
        stop.getTime() > now + 7 * 86400000)
    ) {
      fail(t, Error('Choose a stop time after the first check and within the next seven days.'));
      return;
    }
    const body = {
      manifest_version: t.scope.version,
      enabled: true,
      interval_hours: hours,
      ...(firstRead ? { first_read_at: firstRead.toISOString() } : {}),
      ...(stop ? { stop_at: stop.toISOString() } : {}),
      ...(reportId === inventoryOption ? { mode: 'inventory' } : { report_id: reportId }),
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
    reviewPanel,
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
