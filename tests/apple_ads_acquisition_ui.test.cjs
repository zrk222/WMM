const { test } = require('node:test');
const assert = require('node:assert/strict');

async function renderer() {
  const { money } = await import('../mission_control/static/app-money.mjs');
  const { appleAcquisitionTable } =
    await import('../mission_control/static/apple-ads-acquisition-table.mjs');
  return (result) =>
    appleAcquisitionTable(result, {
      money: (value, unit) => money(value, unit, 'en-US'),
      esc: (value) => String(value).replaceAll('<', '&lt;'),
    });
}

test('saved report shows cost and new downloads as distinct from other outcomes', async () => {
  const render = await renderer();
  const result = render({
    campaign_acquisition: {
      rows: [
        {
          campaign_id: '<unsafe>',
          first_time_downloads: 3,
          status: 'AVAILABLE',
          billing_currency: 'USD',
          cost_per_new_download_minor: '304.0100',
        },
      ],
    },
  });
  assert.match(result, /Cost per new download/);
  assert.match(result, /USD\s+3\.0401/);
  assert.match(result, /First-time downloads/);
  assert.match(result, /Redownloads and paid subscriptions are separate/);
  assert.match(result, /scope="row">&lt;unsafe>/);
  assert.doesNotMatch(result, /<unsafe>/);
});

test('open and incomplete receipts give repair guidance and never show zero cost', async () => {
  const render = await renderer();
  assert.equal(render({ operation: 'campaign_report' }), '');
  const result = render({
    campaign_acquisition: {
      rows: [
        { campaign_id: '42', first_time_downloads: 0, status: 'OPEN_REPORT_WINDOW' },
        { campaign_id: '43', first_time_downloads: null, status: 'MISSING_FIRST_DOWNLOADS' },
      ],
    },
  });
  assert.match(result, /Choose an end date that has finished in UTC/);
  assert.match(result, /First-time downloads were not reported/);
  assert.match(result, /<td>0<\/td><td>Unavailable<\/td>/);
  assert.doesNotMatch(result, /USD\s+0/);
});
