import { $, api, button, esc, state } from './app.mjs';
import { modal } from './app-ui.mjs';
import { WMMPageReports } from './feature-apis.mjs';
('use strict');
/* Exact owner monitoring preferences; domain services retain effect authority. */
const monitorRuleName = (name) =>
  ({
    configuration_drift:
      'Pause an active campaign when its configuration changed or could not be confirmed',
    active_after_end: 'Pause if the campaign is still active after its approved end',
  })[name] || 'Unavailable condition';
const monitorPauseEvidence =
  'Every pause needs a matching provider observation no more than 30 seconds old and current permission.';

const WMMCampaignMonitor = (() => {
  let active = null;
  let inspection = null;
  const current = () => ({
    app: state.app,
    version: state.workspace.app.version,
    principal: state.workspace.identity?.principal,
  });
  const equal = (a, b) => a.app === b.app && a.version === b.version && a.principal === b.principal;
  function valid(ticket) {
    return (
      active === ticket &&
      equal(ticket.scope, current()) &&
      ticket.node?.isConnected &&
      $('#modal').open
    );
  }
  function options(snapshot) {
    return snapshot.intents.filter(
      (r) => r.scope_id === snapshot.scope.scope_id && r.request_hash && r.id,
    );
  }
  const paidTarget = (row) => row?.kind === 'AD';
  function selectedRows(form, rows) {
    const ids = new Set(new FormData(form).getAll('targets'));
    return rows.filter((row) => ids.has(row.id));
  }
  function pauseEligibility(rows, selected) {
    if (!rows.some(paidTarget))
      return {
        available: false,
        reason:
          'No saved paid campaign is in this scope. Page posts are read-only; protective pause is unavailable.',
      };
    if (!selected.some(paidTarget))
      return {
        available: false,
        reason: 'Select a paid campaign to enable protective pause. Page posts remain read-only.',
      };
    return {
      available: true,
      reason:
        'Protective pause is available for review on the selected paid campaign. Approval and each provider readback remain separate.',
    };
  }
  function pauseMarkup(rows) {
    const pauseState = pauseEligibility(rows, []);
    return (
      '<fieldset data-pause-controls aria-describedby="pause-reason"><legend>Optional protective pause</legend><p id="pause-reason" data-pause-status role="status" aria-live="polite">' +
      esc(pauseState.reason) +
      '</p><p class="description">' +
      esc(monitorPauseEvidence) +
      '</p><label class="check-row"><input name="configuration_drift" type="checkbox" disabled>' +
      esc(monitorRuleName('configuration_drift')) +
      '.</label><label class="check-row"><input name="active_after_end" type="checkbox" disabled>' +
      esc(monitorRuleName('active_after_end')) +
      '.</label><label class="field">Maximum protective pause attempts<input ' +
      'name="max_pause_attempts" type="number" min="0" max="20" value="0" required readonly ' +
      'aria-describedby="pause-reason"></label></fieldset>'
    );
  }
  function syncPauseControls(form, rows) {
    if (
      !form ||
      typeof form.querySelector !== 'function' ||
      typeof form.querySelectorAll !== 'function'
    )
      return;
    const pauseState = pauseEligibility(rows, selectedRows(form, rows));
    for (const input of form.querySelectorAll('[data-pause-controls] input[type="checkbox"]')) {
      input.disabled = !pauseState.available;
      if (!pauseState.available) input.checked = false;
    }
    const attempts = form.querySelector('[data-pause-controls] input[name="max_pause_attempts"]');
    if (attempts) {
      if (!pauseState.available) attempts.value = '0';
      attempts.readOnly = !pauseState.available;
    }
    const status = form.querySelector('[data-pause-status]');
    if (status) status.textContent = pauseState.reason;
  }
  function proposal(values, selected, scope, clock = Date.now()) {
    const targets = selected.map((r) => ({ intent_id: r.id, request_hash: r.request_hash }));
    if (
      scope.status !== 'ACTIVE' ||
      !targets.length ||
      targets.length > 20 ||
      selected.some((r) => r.scope_id !== scope.scope_id) ||
      new Set(targets.map((t) => t.intent_id)).size !== targets.length
    )
      throw Error('Choose existing intents in an active scope.');
    const number = (name, min, max) => {
      const n = Number(values[name]);
      if (!Number.isSafeInteger(n) || n < min || n > max)
        throw Error('Use the displayed finite monitoring allowances.');
      return n;
    };
    const expiry = new Date(values.expires_at);
    if (
      !Number.isFinite(expiry.getTime()) ||
      expiry.getTime() <= clock ||
      expiry.getTime() > Date.parse(scope.expires_at)
    )
      throw Error('Choose a future expiry within the campaign scope.');
    const conditions = ['configuration_drift', 'active_after_end'].filter(
      (k) => values[k] === 'on',
    );
    const pauses = number('max_pause_attempts', 0, 20);
    if (Boolean(conditions.length) !== Boolean(pauses))
      throw Error(
        'Select protective conditions and a positive finite pause allowance together, or set pause attempts to zero.',
      );
    if (conditions.length && !selected.some(paidTarget))
      throw Error(
        'Protective pause requires a selected paid campaign intent. Page posts are read-only.',
      );
    return {
      scope_id: scope.scope_id,
      targets,
      cadence_seconds: number('cadence_seconds', 30, 3600),
      expires_at: expiry.toISOString(),
      max_runs: number('max_runs', 1, 100),
      max_provider_units: number('max_provider_units', 1, 160),
      max_pause_attempts: pauses,
      protective_conditions: conditions,
    };
  }
  async function open() {
    const scope = current();
    modal(
      'Campaign monitoring',
      '<div id="monitor-loading" class="modal-content"><p role="status">Reading your campaign scopes and saved monitors…</p></div>',
    );
    const ticket = (active = { scope, node: $('#monitor-loading') });
    try {
      const [history, monitors] = await Promise.all([
        api('/api/apps/' + scope.app + '/campaigns/history', {}),
        api('/api/apps/' + scope.app + '/campaign-monitor/history', {}),
      ]);
      if (!valid(ticket)) return;
      modal(
        'Monitor approved work',
        '<div id="monitor-home" class="modal-content"><p>Choose an active scope with saved delivery intents. You approve ' +
          'exact monitoring targets, limits and optional protective pause conditions. Monitoring creates no posts or ' +
          'ads.</p><h3>Campaign scopes</h3>' +
          history.scopes
            .filter((s) => s.status === 'ACTIVE')
            .map(
              (s) =>
                '<p>Page ' +
                esc(s.page_id) +
                ' · ' +
                esc(s.ad_account_id ? 'Ad account ' + s.ad_account_id : 'Organic publishing') +
                ' · scope ' +
                esc(s.scope_id) +
                ' · expires ' +
                esc(s.expires_at) +
                ' ' +
                button(
                  'Choose scope to monitor',
                  'campaign-monitor-select',
                  'data-id="' + esc(s.scope_id) + '"',
                ) +
                '</p>',
            )
            .join('') +
          '<h3>Saved monitors</h3>' +
          (monitors.monitors
            .map(
              (m) =>
                '<p>' +
                esc(m.effective_status) +
                ' · ' +
                esc(m.id) +
                ' ' +
                button(
                  'Inspect monitor',
                  'campaign-monitor-status',
                  'data-id="' + esc(m.id) + '"',
                ) +
                '</p>',
            )
            .join('') || '<p>No saved monitoring plan. Choose a scope above.</p>') +
          '</div>',
      );
      active = { scope, node: $('#monitor-home') };
    } catch (e) {
      if (valid(ticket)) ticket.node.textContent = e.message;
    }
  }
  async function choose(id) {
    const previous = active;
    if (!previous || !valid(previous) || previous.pending) return;
    previous.pending = true;
    try {
      const snapshot = await api('/api/apps/' + previous.scope.app + '/campaigns/status', {
        scope_id: id,
      });
      if (!valid(previous)) return;
      const rows = options(snapshot);
      if (snapshot.scope.status !== 'ACTIVE')
        throw Error(
          'This campaign scope is no longer active. Review its saved receipt in Campaigns before monitoring.',
        );
      if (!rows.length)
        throw Error(
          'This scope has no saved Page post or paid campaign to monitor. Review the campaign in Campaigns and save a delivery intent first.',
        );
      modal(
        'Set finite monitoring limits',
        '<form id="campaign-monitor-form" class="modal-content"><p>WMM reads only the selected saved intents while this ' +
          'host is running. Pausing needs the separate conditions below; uncertainty alone never authorizes a repeated ' +
          'mutation.</p><fieldset><legend>Exact saved delivery intents</legend>' +
          rows
            .map(
              (r) =>
                '<label class="check-row"><input type="checkbox" name="targets" value="' +
                esc(r.id) +
                '">' +
                esc(r.kind === 'AD' ? 'Paid campaign' : 'Page post') +
                ' · ' +
                esc(r.id) +
                ' · ' +
                esc(r.status) +
                '</label>',
            )
            .join('') +
          '</fieldset><label class="field">Read interval in seconds<input name="cadence_seconds" type="number" min="30" ' +
          'max="3600" value="300" required></label><label class="field">Maximum monitoring runs<input name="max_runs" ' +
          'type="number" min="1" max="100" value="10" required></label><label class="field">Maximum provider boundary ' +
          'units<input name="max_provider_units" type="number" min="1" max="160" value="80" required></label><label ' +
          'class="field">Monitoring expiry (local time)<input name="expires_at" type="datetime-local" required></label>' +
          '<p>Must expire by ' +
          esc(snapshot.scope.expires_at) +
          '. Provider read allowances are independent of emergency pause allowances.</p>' +
          pauseMarkup(rows) +
          '<p>Media ' +
          'commitments stay held after pause. Reported spend may lag; this monitor does not enforce a real-time spend ' +
          'threshold.</p><p id="monitor-error" role="alert"></p><button type="submit" class="button primary">Review exact ' +
          'monitoring plan</button>' +
          button('Cancel', 'close') +
          '</form>',
      );
      const form = $('#campaign-monitor-form');
      if (form && form.addEventListener) {
        syncPauseControls(form, rows);
        form.addEventListener('change', (event) => {
          if (event.target.name === 'targets') syncPauseControls(form, rows);
        });
      }
      active = { scope: previous.scope, node: form, snapshot, rows };
    } catch (e) {
      if (valid(previous)) previous.node.textContent = e.message;
    } finally {
      previous.pending = false;
    }
  }
  const needsRepair = (data) => data.evidence_unavailable || !data.summary?.proposal;
  const repairNotice =
    'Saved monitor approval evidence is unavailable. Check campaign receipts before approving further monitoring.';
  function summary(data, rows = []) {
    if (needsRepair(data)) return '<p role="alert">' + esc(repairNotice) + '</p>';
    const p = data.summary.proposal;
    return (
      '<p>Scope ' +
      esc(p.scope_id) +
      ' · ' +
      esc(p.targets.length) +
      ' exact intents.</p><p>Every ' +
      esc(p.cadence_seconds) +
      ' seconds · expires ' +
      esc(p.expires_at) +
      '. Runs ' +
      esc(p.max_runs) +
      ' · provider units ' +
      esc(p.max_provider_units) +
      ' · pause attempts ' +
      esc(p.max_pause_attempts) +
      '.</p><p>Protective rules: ' +
      esc(p.protective_conditions.map(monitorRuleName).join('; ') || 'None; read-only monitoring') +
      (p.protective_conditions.length ? '. ' + esc(monitorPauseEvidence) : '') +
      '</p>' +
      (p.protective_conditions.length
        ? '<p>Protective pause applies only to paid campaign targets eligible at pause time. This review does not approve or execute a pause; activation and each provider readback remain separate.</p>'
        : '') +
      '<details><summary>Exact target IDs and approval binding</summary><ul>' +
      p.targets
        .map((t) => {
          const row = rows.find((item) => item.id === t.intent_id);
          const kind = row ? (row.kind === 'AD' ? ' · paid campaign' : ' · Page post') : '';
          return '<li>' + esc(t.intent_id) + ' · ' + esc(t.request_hash) + esc(kind) + '</li>';
        })
        .join('') +
      '</ul><p>Summary hash ' +
      esc(data.summary_hash) +
      '</p></details>'
    );
  }
  async function submit(form) {
    const t = active;
    if (!t || !valid(t) || t.pending) return;
    t.pending = true;
    const submit = form.querySelector('[type=submit]');
    submit.disabled = true;
    try {
      const values = Object.fromEntries(new FormData(form)),
        ids = new FormData(form).getAll('targets'),
        chosen = t.rows.filter((r) => ids.includes(r.id));
      const body = proposal(values, chosen, t.snapshot.scope);
      const data = await api('/api/apps/' + t.scope.app + '/campaign-monitor/prepare', {
        proposal: body,
      });
      if (!valid(t)) return;
      modal(
        'Approve this monitoring plan',
        '<div id="monitor-review" class="modal-content"><h3>Review exact monitoring authority</h3>' +
          summary(data, t.rows) +
          '<p>Activation permits the existing worker to read these targets and perform only the selected protective ' +
          'pauses. It cannot publish, create, activate or increase an ad budget. Work stops at expiry or OFF.</p><p ' +
          'id="monitor-error" role="alert"></p>' +
          button('Approve exact monitor', 'campaign-monitor-activate', '', 'primary') +
          button('Cancel', 'close') +
          '</div>',
      );
      active = { scope: t.scope, node: $('#monitor-review'), data };
    } catch (e) {
      if (valid(t)) $('#monitor-error').textContent = e.message;
    } finally {
      t.pending = false;
      submit.disabled = false;
    }
  }
  function nextStep(data) {
    if (data.effective_status === 'OFF') return null;
    if (needsRepair(data)) return repairNotice;
    if (data.effective_status !== 'BLOCKED') return null;
    switch (data.attention) {
      case 'VERIFY_PROVIDER':
        return 'Check the campaign in Meta and compare it with the saved receipt before trying again. WMM will not retry an uncertain action.';
      case 'REVIEW_EXPIRY':
        return 'This monitoring approval expired. Review a new plan if you want WMM to keep watching this campaign.';
      case 'REVIEW_ALLOWANCE':
        return 'WMM used the approved number of checks or requests. Review the saved result before approving more monitoring.';
      case 'REVIEW_PAUSE_ELIGIBILITY':
        return 'This saved monitor requests protective pause for a Page post. Page posts are read-only; approve a new read-only plan without pause conditions, or turn this monitor OFF.';
      default:
        return 'Check the connected account and campaign approval, then review the saved receipt before approving another monitor.';
    }
  }
  function progress(data) {
    const repair = needsRepair(data);
    const last = repair ? null : data.last_observation;
    return (
      '<h3>' +
      esc(
        data.effective_status === 'ACTIVE'
          ? 'Monitoring active'
          : data.effective_status === 'OFF'
            ? 'Monitoring off'
            : 'Monitoring needs attention',
      ) +
      '</h3><p>' +
      esc(
        nextStep(data) ||
          (data.effective_status === 'OFF'
            ? 'Future monitoring is stopped. Existing campaign effects keep their own status.'
            : 'The approved worker checks these exact targets within the limits below.'),
      ) +
      '</p>' +
      summary(data) +
      '<dl class="summary-grid"><div><dt>Runs queued</dt><dd>' +
      esc(data.runs) +
      '</dd></div><div><dt>Provider units reserved</dt><dd>' +
      esc(data.provider_units) +
      '</dd></div><div><dt>Pause attempts reserved</dt><dd>' +
      esc(data.pause_attempts) +
      '</dd></div></dl><h3>Last saved observation</h3>' +
      (last
        ? '<p>Worker result ' +
          esc(last.status) +
          ' · ' +
          esc(last.updated) +
          '</p>' +
          (last.external_execution === 'MONITOR_INTERRUPTED_UNCONFIRMED'
            ? '<p>The worker stopped before it could confirm the provider result. Inspect the saved campaign and verify its current state before taking another action.</p>'
            : '') +
          '<details><summary>Saved job identity</summary><p>' +
          esc(last.job_id) +
          '</p></details>' +
          (last.observations || [])
            .map(
              (r) =>
                '<article><h4>' +
                esc(
                  r.protective_pause === 'PAUSED_campaign'
                    ? 'Protective pause verified'
                    : r.status === 'UNKNOWN'
                      ? 'Delivery needs reconciliation'
                      : 'Provider observation saved',
                ) +
                '</h4><p>' +
                esc(r.status) +
                ' · ' +
                esc(r.recovery || 'No ownership conflict recorded') +
                '</p><details><summary>Exact intent identity</summary><p>' +
                esc(r.intent_id) +
                '</p></details></article>',
            )
            .join('')
        : repair
          ? '<p>Saved observations cannot be projected until the approval evidence is repaired.</p>'
          : '<p>No completed monitoring observation is recorded yet.</p>') +
      '<p>WMM must stay running. Inspect uncertainty before any retry; OFF stops future monitoring and does not pause ' +
      'an already running ad. Campaign pause has its own control and readback.</p><p id="monitor-error" role="alert"></p>' +
      button(
        'Refresh monitor receipts',
        'campaign-monitor-status',
        'data-id="' + esc(data.id) + '"',
      ) +
      button('Turn monitor OFF', 'campaign-monitor-off') +
      button('Monitor report / Save PDF', 'campaign-monitor-report')
    );
  }
  async function inspect(id) {
    const old = active && valid(active) ? active : null;
    if (old?.pending) return;
    const remains = (request) =>
      equal(request.scope, current()) &&
      request.open === $('#modal').open &&
      request.body === $('#modal-body').firstElementChild &&
      request.view === state.view;
    if (inspection && remains(inspection)) return;
    const start = {
      scope: current(),
      open: $('#modal').open,
      body: $('#modal-body').firstElementChild,
      view: state.view,
    };
    inspection = start;
    const sameView = () => inspection === start && remains(start) && (!old || valid(old));
    if (old) old.pending = true;
    try {
      const data = await api('/api/apps/' + start.scope.app + '/campaign-monitor/status', {
        monitor_id: id,
      });
      if (!sameView()) return;
      modal(
        'Monitor saved work',
        '<div id="monitor-progress" class="modal-content">' + progress(data) + '</div>',
      );
      active = { scope: start.scope, node: $('#monitor-progress'), data };
    } catch (e) {
      if (old && sameView()) {
        const error = old.node.querySelector('#monitor-error');
        if (error) error.textContent = e.message;
        else old.node.textContent = e.message;
      } else if (sameView()) throw e;
    } finally {
      if (old) old.pending = false;
      if (inspection === start) inspection = null;
    }
  }
  function report(data, base) {
    const repair = needsRepair(data);
    const p = data.summary?.proposal;
    return {
      ...base,
      title: 'Campaign monitoring',
      purpose: 'Inspect exact saved monitor authority, resource use and job receipts.',
      cohorts: [],
      metrics: [
        {
          label: 'Monitor state',
          value: data.effective_status,
          unit: 'state',
          source: 'Saved monitor authority',
        },
        {
          label: 'Runs queued',
          value: data.runs,
          unit: 'count',
          source: 'Saved monitor allowance',
        },
        {
          label: 'Provider boundary units',
          value: data.provider_units,
          unit: 'reserved units',
          source: 'Saved monitor allowance',
        },
        {
          label: 'Protective pause attempts',
          value: data.pause_attempts,
          unit: 'reserved attempts',
          source: 'Saved monitor allowance',
        },
      ],
      notes: repair
        ? [
            'Monitor ' + data.id,
            repairNotice,
            'Approved scope, targets and saved observations cannot be projected from unavailable evidence.',
            'OFF stops future monitoring; existing campaign effects keep their own status. Verify campaign receipts before another action.',
            'Private copy, raw provider payloads, rights prose and credentials are excluded.',
          ]
        : [
            'Monitor ' + data.id + '; summary ' + data.summary_hash,
            'Scope ' + p.scope_id + '; expires ' + p.expires_at,
            'Exact target IDs: ' + p.targets.map((t) => t.intent_id).join(', '),
            'Last job ' +
              (data.last_observation?.job_id || 'None') +
              ' · ' +
              (data.last_observation?.status || 'Not recorded') +
              (data.last_observation?.external_execution === 'MONITOR_INTERRUPTED_UNCONFIRMED'
                ? ' - provider result unconfirmed after worker interruption. Inspect the saved campaign before taking another action.'
                : ''),
            ...(nextStep(data) ? [nextStep(data)] : []),
            'Saved observations are not real-time spend enforcement, app installs or causal growth.',
            'Private copy, raw provider payloads, rights prose and credentials are excluded.',
          ],
    };
  }
  async function action(node) {
    const kind = node.dataset.action;
    if (kind === 'campaign-monitor-open') return open();
    if (kind === 'campaign-monitor-select') return choose(node.dataset.id);
    if (kind === 'campaign-monitor-status') return inspect(node.dataset.id);
    const t = active;
    if (!t || !valid(t) || t.pending) return;
    t.pending = true;
    node.disabled = true;
    try {
      if (kind === 'campaign-monitor-report')
        return WMMPageReports.openReport(report(t.data, WMMPageReports.model(state)), window);
      if (kind === 'campaign-monitor-activate')
        await api('/api/apps/' + t.scope.app + '/campaign-monitor/activate', {
          monitor_id: t.data.id,
          summary_hash: t.data.summary_hash,
        });
      else if (kind === 'campaign-monitor-off')
        await api('/api/apps/' + t.scope.app + '/campaign-monitor/off', {
          monitor_id: t.data.id,
          version: t.data.version,
        });
      else return;
      if (valid(t)) {
        t.pending = false;
        return inspect(t.data.id);
      }
    } catch (e) {
      if (valid(t)) $('#monitor-error').textContent = e.message;
    } finally {
      t.pending = false;
      node.disabled = false;
    }
  }
  return {
    open,
    choose,
    submit,
    proposal,
    options,
    pauseEligibility,
    pauseMarkup,
    syncPauseControls,
    selectedRows,
    summary,
    progress,
    inspect,
    report,
    action,
  };
})();

export { WMMCampaignMonitor, monitorPauseEvidence, monitorRuleName };
