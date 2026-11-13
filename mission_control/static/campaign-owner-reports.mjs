import { $, api, button, esc, state } from './app.mjs';
import { modal } from './app-ui.mjs';
import { WMMPageReports } from './feature-apis.mjs';
('use strict');
const WMMOwnerReports = (() => {
  let active = null;
  const context = () => ({
    app: state.app,
    version: state.workspace.app.version,
    principal: state.workspace.identity?.principal,
  });
  const same = (a, b) => a.app === b.app && a.version === b.version && a.principal === b.principal;
  const valid = (t) =>
    active === t && same(t.context, context()) && t.node?.isConnected && $('#modal').open;
  const url = (t, action) => '/api/apps/' + t.context.app + '/campaign-owner-reports/' + action;
  function selection(values, monitors, experiments, scopes = []) {
    const monitor = values.monitor_id ? monitors.find((m) => m.id === values.monitor_id) : null;
    const monitoredScope = monitor?.summary?.proposal?.scope_id;
    if (values.monitor_id && !monitoredScope) throw Error('Select an existing owner monitor.');
    const selectedScope = values.scope_id || null;
    if (selectedScope && !scopes.some((scope) => scope.scope_id === selectedScope))
      throw Error('Select an existing owner campaign.');
    if (selectedScope && monitoredScope && selectedScope !== monitoredScope)
      throw Error('Choose a monitor that belongs to the selected campaign.');
    const scope = selectedScope || monitoredScope;
    if (!scope) throw Error('Choose a saved campaign or its monitor.');
    const experiment = values.experiment_id || null;
    if (experiment && !experiments.some((e) => e.id === experiment))
      throw Error('Select an existing experiment.');
    const start = new Date(values.starts_at),
      end = new Date(values.ends_at);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || start >= end)
      throw Error('Choose a positive review window.');
    return {
      scope_id: scope,
      monitor_id: monitor?.id || null,
      experiment_id: experiment,
      measurement_window: { starts_at: start.toISOString(), ends_at: end.toISOString() },
    };
  }
  async function open() {
    const saved = context();
    modal(
      'Your private campaign reports',
      '<div id="owner-report-loading" class="modal-content"><p role="status">Reading saved report sources…</p></div>',
    );
    const t = (active = { context: saved, node: $('#owner-report-loading') });
    try {
      const [history, monitors, campaigns] = await Promise.all([
        api(url(t, 'history'), {}),
        api('/api/apps/' + saved.app + '/campaign-monitor/history', {}),
        api('/api/apps/' + saved.app + '/campaigns/history', {}),
      ]);
      if (!valid(t)) return;
      const experiments = state.workspace.experiments || [];
      modal(
        'Report what happened',
        '<form id="owner-report-form" class="modal-content"><p>Join saved campaign delivery and monitoring receipts with app measurement evidence. Select the review window; each source keeps its own dates. This creates a private local snapshot and starts no provider read.</p><label class="field">Saved campaign<select name="scope_id"><option value="">Use the selected monitor’s campaign</option>' +
          campaigns.scopes
            .map(
              (scope) =>
                '<option value="' +
                esc(scope.scope_id) +
                '">Facebook Page ' +
                esc(scope.page_id) +
                ' · ' +
                esc(scope.status) +
                ' · ' +
                esc(scope.scope_id) +
                '</option>',
            )
            .join('') +
          '</select></label><label class="field">Saved campaign monitor (optional)<select name="monitor_id"><option value="">No monitor selected</option>' +
          monitors.monitors
            .map(
              (m) =>
                '<option value="' +
                esc(m.id) +
                '">' +
                esc(m.id) +
                ' · ' +
                esc(m.status) +
                '</option>',
            )
            .join('') +
          '</select></label><label class="field">Existing experiment (optional)<select name="experiment_id"><option value="">No experiment selected</option>' +
          experiments
            .map((e) => '<option value="' + esc(e.id) + '">' + esc(e.name || e.id) + '</option>')
            .join('') +
          '</select></label><label class="field">Review window starts (local time)<input type="datetime-local" name="starts_at" required></label><label class="field">Review window ends (local time)<input type="datetime-local" name="ends_at" required></label><label class="field">Report timing<select name="mode"><option value="capture">Save one report now</option><option value="schedule">Review a finite recurring report plan</option></select></label><details><summary>Recurring report limits</summary><label class="field">Interval in seconds<input name="cadence_seconds" type="number" min="30" max="86400" value="86400"></label><label class="field">Maximum reports<input name="max_reports" type="number" min="1" max="100" value="7"></label><label class="field">Plan expiry (local time)<input type="datetime-local" name="expires_at"></label><p>At most seven days. WMM must remain running. Reports stay in this private workspace; nothing is emailed or published.</p></details><p id="owner-report-error" role="alert"></p><button type="submit" class="button primary">Continue with exact sources</button>' +
          button('Cancel', 'close') +
          '</form><section class="modal-content"><h3>Saved report plans</h3>' +
          (history.plans
            .map(
              (p) =>
                '<p>' +
                esc(p.effective_status) +
                ' · ' +
                esc(p.id) +
                ' ' +
                button('Inspect report plan', 'owner-report-plan', 'data-id="' + esc(p.id) + '"') +
                '</p>',
            )
            .join('') || '<p>No saved report plans.</p>') +
          '<h3>Saved private reports</h3>' +
          (history.reports
            .map(
              (r) =>
                '<p>' +
                esc(r.created) +
                ' ' +
                button('Read saved report', 'owner-report-read', 'data-id="' + esc(r.id) + '"') +
                '</p>',
            )
            .join('') || '<p>No saved reports yet.</p>') +
          '</section>',
      );
      active = {
        context: saved,
        node: $('#owner-report-form'),
        monitors: monitors.monitors,
        scopes: campaigns.scopes,
        experiments,
        request_key: crypto.randomUUID(),
      };
    } catch (e) {
      if (valid(t)) t.node.textContent = e.message;
    }
  }
  function schedule(values, chosen, clock = Date.now()) {
    const cadence = Number(values.cadence_seconds),
      count = Number(values.max_reports),
      expiry = new Date(values.expires_at);
    if (
      !Number.isSafeInteger(cadence) ||
      cadence < 30 ||
      cadence > 86400 ||
      !Number.isSafeInteger(count) ||
      count < 1 ||
      count > 100 ||
      !Number.isFinite(expiry.getTime()) ||
      expiry.getTime() <= clock ||
      expiry.getTime() > clock + 7 * 86400000
    )
      throw Error('Choose a finite cadence, count and expiry within seven days.');
    return {
      selection: chosen,
      cadence_seconds: cadence,
      max_reports: count,
      expires_at: expiry.toISOString(),
    };
  }
  async function submit(form) {
    const t = active;
    if (!t || !valid(t) || t.pending) return;
    t.pending = true;
    const submit = form.querySelector('[type=submit]');
    submit.disabled = true;
    try {
      const values = Object.fromEntries(new FormData(form)),
        chosen = selection(values, t.monitors, t.experiments, t.scopes);
      if (values.mode === 'capture') {
        const result = await api(url(t, 'capture'), {
          selection: chosen,
          request_key: t.request_key,
        });
        if (valid(t)) showReport(t, result);
        return;
      }
      const data = await api(url(t, 'prepare'), { proposal: schedule(values, chosen) });
      if (!valid(t)) return;
      modal(
        'Approve private report schedule',
        '<div id="owner-report-review" class="modal-content">' +
          planSummary(data) +
          '<p>This approval permits only private local snapshots of the selected saved evidence. No provider reads, campaign changes or outgoing messages are added.</p><p id="owner-report-error" role="alert"></p>' +
          button('Approve exact report plan', 'owner-report-activate', '', 'primary') +
          button('Cancel', 'close') +
          '</div>',
      );
      active = { context: t.context, node: $('#owner-report-review'), data };
    } catch (e) {
      if (valid(t)) $('#owner-report-error').textContent = e.message;
    } finally {
      t.pending = false;
      submit.disabled = false;
    }
  }
  function planSummary(data) {
    const p = data.summary.proposal;
    return (
      '<h3>' +
      esc(data.effective_status || data.status) +
      '</h3><p>Every ' +
      esc(p.cadence_seconds) +
      ' seconds · at most ' +
      esc(p.max_reports) +
      ' reports · expires ' +
      esc(p.expires_at) +
      '</p><p>Monitor ' +
      esc(p.selection.monitor_id || 'not selected') +
      ' · scope ' +
      esc(p.selection.scope_id) +
      '</p><p>Review window ' +
      esc(p.selection.measurement_window.starts_at) +
      ' to ' +
      esc(p.selection.measurement_window.ends_at) +
      '</p><p>Reports dispatched ' +
      esc(data.reports_dispatched) +
      ' · last job ' +
      esc(data.last_job || 'None') +
      '</p><p>' +
      esc(data.next_action || 'Review the exact saved sources and limits.') +
      '</p><details><summary>Exact approval binding</summary><p>' +
      esc(data.summary_hash) +
      '</p></details>'
    );
  }
  function pauseText(receipt) {
    const r = receipt.pause_readback;
    return r
      ? 'Saved pause read ' +
          r.observed_at +
          ' · configured ' +
          r.configured_status +
          ' · effective ' +
          (r.effective_status ?? 'Unavailable') +
          ' · receipt ' +
          r.sha256 +
          '. This observation describes the campaign at that time. Reported charges may arrive later.'
      : receipt.status === 'PAUSED_campaign'
        ? 'Saved provider pause readback is unavailable. Local status alone does not establish provider confirmation.'
        : '';
  }
  function monitorText(monitor) {
    return monitor.status === 'NOT_SELECTED'
      ? 'No monitor selected. Monitoring results are unavailable.'
      : 'Saved monitor status ' + monitor.status + '.';
  }
  function coverageText(coverage) {
    const { available_rows: available, unknown_rows: unknown } = coverage;
    return `Saved values for ${available} of ${available + unknown} evidence rows. ${unknown} unknown.`;
  }
  function measurementNextStep(report) {
    // Keep measurement guidance visible when the saved next action is an authority reminder.
    if (report.experiment) return '';
    return 'Campaign outcome is unknown. Choose a primary outcome and connect a study with matching dates before judging this campaign. App-wide measurements do not show what this campaign did.';
  }
  function model(saved, base) {
    const r = saved.report;
    return {
      ...base,
      title: 'Private campaign outcome review',
      purpose: 'Read saved delivery receipts beside app measurement coverage.',
      loaded_at: r.observed_at,
      next_step: r.next_action,
      cohorts: [],
      metrics: [
        {
          label: 'Retained media commitment',
          value: r.campaign.retained_commitment_minor,
          unit: 'minor ' + r.campaign.currency,
          source: 'Saved campaign commitments',
        },
        {
          label: 'KPI rows with saved observations',
          value: r.kpi_coverage.available_rows,
          unit: 'rows',
          source: 'Saved source-scoped app evidence',
        },
        {
          label: 'Unknown KPI rows',
          value: r.kpi_coverage.unknown_rows,
          unit: 'rows',
          source: 'Saved source-scoped app evidence',
        },
        ...r.kpis.rows.map((row) => ({
          label: row.metric,
          value: row.observed,
          unit: 'source-scoped',
          source: row.evidence,
        })),
      ],
      notes: [
        'Private report ' + saved.id + '; hash ' + saved.hash + '; source ' + r.source_hash,
        'Requested window ' +
          r.selection.measurement_window.starts_at +
          ' to ' +
          r.selection.measurement_window.ends_at,
        'Source windows retained; app-wide source observations are not filtered to the requested window.',
        coverageText(r.kpi_coverage),
        ...(measurementNextStep(r) ? [measurementNextStep(r)] : []),
        'Saved provider readback: ' +
          r.campaign.provider_readback +
          '. Reported spend is unavailable in this snapshot.',
        monitorText(r.monitor),
        'Campaign delivery and descriptive metric changes do not establish causal installs, revenue or growth.',
        'Comparison ' +
          r.comparison.status +
          '; previous report ' +
          (r.comparison.previous_id || 'None'),
        ...r.comparison.changes.map(
          (c) =>
            c.metric +
            ': ' +
            String(c.previous ?? 'Unknown') +
            ' → ' +
            String(c.current ?? 'Unknown'),
        ),
        ...r.campaign.receipts.map(
          (c) => 'Receipt ' + c.id + ' · ' + c.kind + ' · ' + c.status + ' ' + pauseText(c),
        ),
        r.experiment
          ? 'Experiment ' + r.experiment.id + ' · ' + r.experiment.maturity
          : 'No experiment selected',
        'Private copy, raw provider payloads and credentials are excluded.',
      ],
    };
  }
  function markup(saved) {
    const r = saved.report;
    return (
      '<h3>Your next useful decision</h3><p>' +
      esc(r.next_action) +
      '</p>' +
      (measurementNextStep(r) ? '<p>' + esc(measurementNextStep(r)) + '</p>' : '') +
      '<p>Saved ' +
      esc(r.observed_at) +
      ' · ' +
      esc(r.campaign.status) +
      ' campaign · ' +
      esc(monitorText(r.monitor)) +
      '</p><p>Retained commitment ' +
      esc(r.campaign.retained_commitment_minor) +
      ' minor ' +
      esc(r.campaign.currency) +
      '. ' +
      esc(coverageText(r.kpi_coverage)) +
      '</p><p><strong>Source dates stay separate.</strong> The requested review window does not filter app-wide source observations. Counts and changes do not establish campaign attribution.</p><h3>Saved app measurements</h3>' +
      r.kpis.rows
        .map(
          (row) =>
            '<article class="panel"><h4>' +
            esc(row.metric) +
            '</h4><p>' +
            esc(row.observed ?? 'Unknown') +
            '</p><details><summary>Source evidence and dates</summary><p>' +
            esc(row.evidence) +
            '</p></details></article>',
        )
        .join('') +
      '<h3>Comparison</h3><p>' +
      esc(r.comparison.status) +
      ' · ' +
      esc(r.comparison.changes.length) +
      ' descriptive changes.</p><p>' +
      esc(
        r.experiment
          ? 'Experiment ' + r.experiment.id + ' · ' + r.experiment.maturity
          : 'No experiment selected. App results remain source observations.',
      ) +
      '</p><details><summary>Exact receipts, source window and integrity</summary><p>Window ' +
      esc(r.selection.measurement_window.starts_at) +
      ' to ' +
      esc(r.selection.measurement_window.ends_at) +
      '</p>' +
      r.campaign.receipts
        .map(
          (c) =>
            '<p>' +
            esc(c.id) +
            ' · ' +
            esc(c.kind) +
            ' · ' +
            esc(c.status) +
            '</p>' +
            (pauseText(c) ? '<p>' + esc(pauseText(c)) + '</p>' : ''),
        )
        .join('') +
      '<p>Report ' +
      esc(saved.id) +
      ' · hash ' +
      esc(saved.hash) +
      ' · source ' +
      esc(r.source_hash) +
      '</p></details><p id="owner-report-error" role="alert"></p>' +
      button('Private report / Save PDF', 'owner-report-pdf') +
      button('Return to saved reports', 'owner-report-open')
    );
  }
  function showReport(t, data) {
    modal(
      'Your private campaign outcome review',
      '<div id="owner-report-result" class="modal-content">' + markup(data) + '</div>',
    );
    active = { context: t.context, node: $('#owner-report-result'), data };
  }
  async function inspect(kind, id) {
    const old = active;
    if (!old || !valid(old) || old.pending) return;
    old.pending = true;
    try {
      const data = await api(
        url(old, kind === 'plan' ? 'status' : 'read'),
        kind === 'plan' ? { plan_id: id } : { report_id: id },
      );
      if (!valid(old)) return;
      if (kind !== 'plan') {
        showReport(old, data);
        return;
      }
      modal(
        'Your private report plan',
        '<div id="owner-report-plan" class="modal-content">' +
          planSummary(data) +
          '<p id="owner-report-error" role="alert"></p>' +
          button('Refresh report plan', 'owner-report-plan', 'data-id="' + esc(data.id) + '"') +
          button('Turn report plan OFF', 'owner-report-off') +
          button('Read saved reports', 'owner-report-open') +
          '</div>',
      );
      active = { context: old.context, node: $('#owner-report-plan'), data };
    } catch (e) {
      if (valid(old)) {
        const error = $('#owner-report-error');
        if (error) error.textContent = e.message;
      }
    } finally {
      old.pending = false;
    }
  }
  async function action(node) {
    const name = node.dataset.action;
    if (name === 'owner-report-open') return open();
    if (name === 'owner-report-read') return inspect('report', node.dataset.id);
    if (name === 'owner-report-plan') return inspect('plan', node.dataset.id);
    const t = active;
    if (!t || !valid(t) || t.pending) return;
    t.pending = true;
    node.disabled = true;
    try {
      if (name === 'owner-report-pdf')
        return WMMPageReports.openReport(model(t.data, WMMPageReports.model(state)), window);
      if (name === 'owner-report-activate')
        await api(url(t, 'activate'), { plan_id: t.data.id, summary_hash: t.data.summary_hash });
      else if (name === 'owner-report-off')
        await api(url(t, 'off'), { plan_id: t.data.id, version: t.data.version });
      else return;
      if (valid(t)) {
        t.pending = false;
        return inspect('plan', t.data.id);
      }
    } catch (e) {
      if (valid(t)) $('#owner-report-error').textContent = e.message;
    } finally {
      t.pending = false;
      node.disabled = false;
    }
  }
  return { open, selection, schedule, submit, planSummary, model, markup, inspect, action };
})();

export { WMMOwnerReports };
