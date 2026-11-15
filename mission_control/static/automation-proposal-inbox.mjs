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
    ? `<p>Rule version ${esc(schedule.binding?.saved?.version ?? 'unavailable')} · ${esc(states[schedule.status] || schedule.status)} · ${esc(schedule.run_count)} of ${esc(schedule.max_runs)} reviews.${schedule.next_due ? ` Next: ${esc(savedWhen(schedule.next_due))}.` : ''} ${esc(schedule.reason || '')}</p>${schedule.status === 'ACTIVE' ? button('Turn off reviews', 'automation-proposals-off', `data-version="${esc(schedule.version)}"`) : ''}`
    : '<p>Scheduled reviews are off.</p>';
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
          <p>${row.dismissed_at ? 'Dismissed' : older ? 'From an earlier app version' : 'Ready for review'} · Rule version ${esc(row.rule_version)}.</p>
          ${row.dismissed_at ? '' : button('Dismiss recommendation', 'automation-proposals-dismiss', `data-proposal="${esc(item.id)}"`)}
          <details><summary>Evidence details</summary><p>Receipt ${esc(row.receipt_id)}</p><p>Facts ${esc(item.fact_snapshot_sha256)}</p></details></li>`;
        })
        .join('')}</ul>`
    : '<p>No saved recommendations. Open Saved rule versions and run a version to get started.</p>';
  return (
    timing +
    unknown +
    proposals +
    (value.has_more
      ? '<p>Showing the 50 most recent recommendations, with open items first.</p>'
      : '')
  );
}
