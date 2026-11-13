import assert from 'node:assert/strict';
import test from 'node:test';
import { WMMAnalyticsInventory as inventory } from '../mission_control/static/analytics-inventory.mjs';

const cohort = { kind: 'cohort', created: '2026-11-09T10:00:00+00:00' };
const retention = { kind: 'retention', created: '2026-11-08T10:00:00+00:00' };

test('empty analytics stays unavailable and points to one acquisition step', () => {
  const view = inventory.summary({});
  assert.equal(view.savedCount, 0);
  assert.equal(view.total, 6);
  assert.equal(view.step.id, 'add_acquisition');
  assert.equal(view.counts.cohorts, 0);
  assert.equal(view.areas.find((row) => row.id === 'payments').saved, 'Unavailable');
  assert.equal(view.areas.find((row) => row.id === 'payments').next, 'Review connections');
});

test('measured cohort with no install export points to the MMP export', () => {
  const view = inventory.summary({
    records: [cohort],
    metrics: { cohorts: [{ status: 'MEASURED' }], retention: [], event_ledger: [] },
    measurement_integrity: { state: 'MEASURED', rows: [] },
  });
  assert.equal(view.savedCount, 2);
  assert.equal(view.step.id, 'import_installs');
  assert.equal(view.areas.find((row) => row.id === 'cohorts').saved, '1 saved · 1 measured');
  assert.equal(view.areas.find((row) => row.id === 'cohorts').latest, cohort.created);
});

test('unmeasured cohort is repaired before installs are requested', () => {
  const view = inventory.summary({
    records: [cohort],
    metrics: { cohorts: [{ status: 'UNAVAILABLE' }], retention: [], event_ledger: [] },
  });
  assert.equal(view.step.id, 'repair_cohort');
  assert.equal(view.areas.find((row) => row.id === 'cohorts').saved, '1 saved · 0 measured');
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
    metrics: {
      cohorts: [{ status: 'MEASURED' }],
      retention: [{ mature: true, eligible: 4, retained: 3, rate: 0.75 }],
      event_ledger: [],
    },
    install_attribution: { campaigns: [{}] },
    measurement_integrity: { state: 'MEASURED', rows: [] },
  };
  assert.equal(inventory.summary(ready).step.id, 'inspect_result');
  const missing = { ...ready, records: [], metrics: { ...ready.metrics, retention: [] } };
  assert.equal(inventory.summary(missing).step.id, 'add_retention');
});

test('latest saved picks the newest non-empty timestamp and ignores blanks', () => {
  assert.equal(
    inventory.latestSaved([null, '2026-11-01T00:00:00Z', '', '2026-11-09T00:00:00Z']),
    '2026-11-09T00:00:00Z',
  );
  assert.equal(inventory.latestSaved([null, '']), null);
});

const ledgerRow = {
  cohort: { cohort_id: 'eligible-cohort', ends_at: '2030-01-08', matures_at: '2030-01-15' },
  status: 'SUPPLIED_RECONCILED',
  observability: 'OBSERVED',
  costs_complete: true,
  mature: true,
  installs: 4,
  retained: 3,
  retention_rate: 0.75,
  as_of: '2030-01-16',
};
function ledgerWorkspace(rows, worksheets = []) {
  return {
    metrics: { cohorts: [{ status: 'MEASURED' }], event_ledger: rows, retention: worksheets },
    install_attribution: { campaigns: [{}] },
    measurement_integrity: { state: 'MEASURED', rows: [] },
  };
}
test('eligible ledger retention avoids duplicate worksheet request and labels source counts and window', () => {
  const view = inventory.summary(ledgerWorkspace([ledgerRow]));
  const row = view.areas.find((r) => r.id === 'retention');
  assert.notEqual(row.saved, 'None');
  assert.match(row.saved, /Event ledger/);
  assert.match(row.saved, /3\/4/);
  assert.match(row.saved, /75%/);
  assert.match(row.saved, /2030-01-08.*2030-01-15/);
  assert.doesNotMatch(row.saved, /D7/);
  assert.equal(view.step.id, 'inspect_result');
  assert.equal(view.counts.retention, 1);
});
test('zero is observed but unavailable windows and immature worksheets require evidence repair', () => {
  const zero = inventory.summary(
    ledgerWorkspace([{ ...ledgerRow, retained: 0, retention_rate: 0 }]),
  );
  assert.match(zero.areas.find((r) => r.id === 'retention').saved, /0\/4.*0%/);
  for (const changes of [
    { installs: 0, retained: 0, retention_rate: null },
    { mature: false, retention_rate: null },
    { observability: 'PARTIAL', retention_rate: null },
    { retention_rate: null, status: 'INCONCLUSIVE' },
  ]) {
    const view = inventory.summary(
      ledgerWorkspace(
        [{ ...ledgerRow, ...changes }],
        [{ mature: false, eligible: 4, retained: 1, rate: null, window: 'manual' }],
      ),
    );
    assert.equal(view.step.id, 'repair_retention');
    assert.match(view.areas.find((r) => r.id === 'retention').next, /eligible-cohort/);
    assert.match(view.areas.find((r) => r.id === 'retention').saved, /unavailable/);
  }
});
test('ledger and worksheet windows stay separate without pooling', () => {
  const view = inventory.summary(
    ledgerWorkspace(
      [ledgerRow],
      [{ mature: true, eligible: 8, retained: 2, rate: 0.25, window: 'worksheet window' }],
    ),
  );
  const text = view.areas.find((r) => r.id === 'retention').saved;
  assert.match(text, /Event ledger.*3\/4.*75%/);
  assert.match(text, /Worksheet.*2\/8.*25%/);
  assert.doesNotMatch(text, /5\/12/);
});
