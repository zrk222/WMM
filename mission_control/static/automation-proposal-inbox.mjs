export function proposalInboxMarkup(value, { appVersion, esc, button, savedWhen }) {
  const schedule = value.schedule;
  const states = {
    ACTIVE: 'Scheduled',
    OFF: 'Off',
    EXPIRED: 'Ended',
    EXHAUSTED: 'Reached the run limit',
    BLOCKED: 'Needs review',
  };
  const timing = schedule
    ? `<p>Rule version ${esc(schedule.binding?.saved?.version ?? 'unavailable')} Â· ${esc(states[schedule.status] || schedule.status)} Â· ${esc(schedule.run_count)} of ${esc(schedule.max_runs)} reviews.${schedule.next_due ? ` Next: ${esc(savedWhen(schedule.next_due))}.` : ''} ${esc(schedule.reason || '')}</p>${schedule.status === 'ACTIVE' ? button('Turn off reviews', 'automation-proposals-off', `data-version="${esc(schedule.version)}"`) : ''}`
    : '<p>Scheduled reviews are off.</p>';
  const savedReport = schedule?.saved_report;
  const result = savedReport
    ? `<p><strong>Private report saved.</strong> Read it in your private campaign reports.</p>
        ${button('Open private campaign reports', 'owner-report-open')}
        <details><summary>Latest report receipt</summary><p>Report ${esc(savedReport.report_id)}</p><p>Fingerprint ${esc(savedReport.report_hash)}</p></details>`
    : '';
  const template = schedule?.binding?.report_integration;
  const integration =
    schedule?.mode === 'SAVE_PRIVATE_REPORT' && template
      ? `<p>Private reports saved: ${esc(schedule.saved_report_count ?? (savedReport ? 1 : 0))} of ${esc(template.max_reports ?? 1)}. Template: ${esc(template.report_id.slice(0, 8))}.</p>`
      : '';
  const outcomes = (value.latest_run?.results || []).filter((row) => row.status === 'UNKNOWN');
  const unknown = outcomes.length
    ? `<p>${esc(outcomes.length)} rules need more evidence.</p><details><summary>Missing or incompatible evidence</summary><ul>${outcomes.map((row) => `<li>${esc(row.rule_id)}: ${esc([...(row.missing || []), ...(row.incompatible || [])].join(', '))}</li>`).join('')}</ul></details>`
    : '';
  const proposals = value.proposals.length
    ? `<ul>${value.proposals
        .map((row) => {
          const item = row.proposal;
          const older = row.app_version !== appVersion;
          return `<li><strong>${esc(item.action.replaceAll('_', ' '))}</strong><p>${esc(item.reason)}</p>
          <p>${row.dismissed_at ? 'Dismissed' : older ? 'From an earlier app version' : 'Ready for review'} Â· Rule version ${esc(row.rule_version)}.</p>
          ${row.dismissed_at ? '' : button('Dismiss recommendation', 'automation-proposals-dismiss', `data-proposal="${esc(item.id)}"`)}
          <details><summary>Evidence details</summary><p>Receipt ${esc(row.receipt_id)}</p><p>Facts ${esc(item.fact_snapshot_sha256)}</p></details></li>`;
        })
        .join('')}</ul>`
    : '<p>No saved recommendations. Open Saved rule versions and run a version to get started.</p>';
  return (
    timing +
    integration +
    result +
    unknown +
    proposals +
    (value.has_more
      ? '<p>Showing the 50 most recent recommendations, with open items first.</p>'
      : '')
  );
}

export function reportTemplates(history, appVersion) {
  return (history?.reports ?? []).filter(
    (entry) => entry.report?.source?.app_version === appVersion,
  );
}

export function proposalScheduleMarkup(saved, schedule, reports, { esc, button, savedWhen }) {
  const attrs = `data-rule-version="${esc(saved.version)}" data-rule-hash="${esc(saved.hash)}" data-version="${esc(schedule?.version ?? '')}"`;
  const options = reports
    .map((entry, index) => {
      const window = entry.report.selection.measurement_window;
      return `<option value="${index}">Saved ${esc(savedWhen(entry.created))} · ${esc(window.starts_at.slice(0, 10))} to ${esc(window.ends_at.slice(0, 10))} · ${esc(entry.id.slice(0, 8))}</option>`;
    })
    .join('');
  return `<fieldset><legend>Schedule local review for rule version ${esc(saved.version)}</legend>
    <p>WMM uses saved evidence while it runs. It does not post, spend, or contact providers. ${schedule?.status === 'ACTIVE' ? 'Starting replaces the existing schedule.' : ''}</p>
    <div class="form-grid"><label class="field">Hours between reviews<input id="proposal-interval" type="number" min="1" max="24" value="24" required></label>
    <label class="field">End after days<input id="proposal-days" type="number" min="2" max="7" value="7" required></label>
    <label class="field">Maximum reviews<input id="proposal-count" type="number" min="1" max="30" value="6" required></label></div>
    ${
      options
        ? `<label class="field">When a Results review is ready<select id="proposal-report-template">
    <option value="">Save a recommendation only</option>${options}</select></label>
    <div id="proposal-report-settings" hidden>
      <label class="field">Maximum private report saves<input id="proposal-report-count" type="number" min="1" max="6" step="1" value="1" aria-describedby="proposal-report-help" required disabled></label>
      <p id="proposal-report-help">Starting approves up to this many private saves for this app and the exact template’s sources and dates. If a study is selected, its dates must match. The first report saves when the evidence meets the saved rules. Each later save also needs a new revision of the evidence WMM has retained. Reports stay in this app’s private history.</p>
    </div>`
        : '<p>To save reports from this schedule, first save a private campaign report for this app or selected study.</p>'
    }
    ${button('Start scheduled reviews', 'automation-proposals-start', attrs)}</fieldset>`;
}
