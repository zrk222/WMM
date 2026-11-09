const assert = require('node:assert/strict');
const test = require('node:test');
const inventory = require('../mission_control/static/analytics-inventory.js');

const cohort = { kind: 'cohort', created: '2026-11-09T10:00:00+00:00' };
const retention = { kind: 'retention', created: '2026-11-08T10:00:00+00:00' };

test('empty analytics stays unavailable and points to one acquisition step', () => {
  const view = inventory.summary({});
  assert.equal(view.savedCount, 0);
  assert.equal(view.total, 6);
  assert.equal(view.step.id, 'add_acquisition');
  assert.equal(view.counts.cohorts, 0);
  assert.equal(view.areas.find(row => row.id === 'payments').saved, 'Unavailable');
  assert.equal(view.areas.find(row => row.id === 'payments').next, 'Review connections');
});

test('measured cohort with no install export points to the MMP export', () => {
  const view = inventory.summary({
    records: [cohort],
    metrics: { cohorts: [{ status: 'MEASURED' }], retention: [], event_ledger: [] },
    measurement_integrity: { state: 'MEASURED', rows: [] },
  });
  assert.equal(view.savedCount, 2);
  assert.equal(view.step.id, 'import_installs');
  assert.equal(view.areas.find(row => row.id === 'cohorts').saved, '1 saved · 1 measured');
  assert.equal(view.areas.find(row => row.id === 'cohorts').latest, cohort.created);
});

test('unmeasured cohort is repaired before installs are requested', () => {
  const view = inventory.summary({
    records: [cohort],
    metrics: { cohorts: [{ status: 'UNAVAILABLE' }], retention: [], event_ledger: [] },
  });
  assert.equal(view.step.id, 'repair_cohort');
  assert.equal(view.areas.find(row => row.id === 'cohorts').saved, '1 saved · 0 measured');
});

test('payment repair precedes retention advice', () => {
  const view = inventory.summary({
    metrics: { cohorts: [{ status: 'MEASURED' }], retention: [], event_ledger: [] },
    install_attribution: { campaigns: [{ last_observed_at: '2026-11-09T11:00:00+00:00' }] },
    measurement_integrity: { state: 'UNAVAILABLE' },
  });
  assert.equal(view.step.id, 'repair_payments');
});

test('retention is the last missing prerequisite before inspection', () => {
  const ready = {
    records: [retention],
    metrics: { cohorts: [{ status: 'MEASURED' }], retention: [{ mature: true }], event_ledger: [] },
    install_attribution: { campaigns: [{}] },
    measurement_integrity: { state: 'MEASURED', rows: [] },
  };
  assert.equal(inventory.summary(ready).step.id, 'inspect_result');
  const missing = { ...ready, records: [], metrics: { ...ready.metrics, retention: [] } };
  assert.equal(inventory.summary(missing).step.id, 'add_retention');
});

test('latest saved picks the newest non-empty timestamp and ignores blanks', () => {
  assert.equal(inventory.latestSaved([null, '2026-11-01T00:00:00Z', '', '2026-11-09T00:00:00Z']), '2026-11-09T00:00:00Z');
  assert.equal(inventory.latestSaved([null, '']), null);
});
