export function appleAcquisitionTable(result, { money, esc }) {
  const receipt = result.campaign_acquisition;
  if (!receipt || !Array.isArray(receipt.rows) || receipt.rows.length === 0) return '';
  const labels = {
    AVAILABLE: 'Reported',
    INCOMPLETE_REPORT: 'Only part of the report was returned',
    OPEN_REPORT_WINDOW: 'Choose an end date that has finished in UTC',
    NO_CAMPAIGN_ROW: 'Apple returned no row for this campaign',
    MISSING_SPEND: 'Spend was not reported',
    MISSING_FIRST_DOWNLOADS: 'First-time downloads were not reported',
    NO_REPORTED_SPEND: 'No reported spend',
    NO_FIRST_DOWNLOADS: 'No first-time downloads',
  };
  const rows = receipt.rows
    .map((row) => {
      const raw = row.cost_per_new_download_minor;
      const available =
        row.status === 'AVAILABLE' && typeof raw === 'string' && /^[0-9]+\.[0-9]{4}$/.test(raw);
      const cost = available ? money(Number(raw), row.billing_currency) : 'Unavailable';
      return `<tr><th scope="row">${esc(row.campaign_id)}</th><td>${esc(row.first_time_downloads ?? 'Unavailable')}</td><td>${esc(cost)}</td><td>${esc(labels[row.status] || 'Needs review')}</td></tr>`;
    })
    .join('');
  return `<section aria-labelledby="apple-cost-heading"><h3 id="apple-cost-heading">Cost to acquire a new download</h3><p>Apple Ads reports first-time downloads for the selected campaign and UTC dates. Redownloads and paid subscriptions are separate.</p><div class="table-wrap"><table class="result-table"><caption>Apple Ads campaign acquisition</caption><thead><tr><th scope="col">Campaign</th><th scope="col">First-time downloads</th><th scope="col">Cost per new download</th><th scope="col">Evidence status</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}
