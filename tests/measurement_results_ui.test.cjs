const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('./helpers/module-source.cjs');
const source = fs.readFileSync('mission_control/static/app-events.mjs', 'utf8');
const context = {};
vm.createContext(context);
vm.runInContext(
  source.slice(
    source.indexOf('function cohortPayload('),
    source.indexOf('async function formSubmit('),
  ),
  context,
);

test('legacy cohort submission removes empty optional controls without changing original fields', () => {
  const original = { cohort_id: 'cohort-one', currency: 'USD', source: 'receipt' };
  const value = context.cohortPayload({
    ...original,
    economics_cost_basis: '',
    economics_currency: 'USD',
  });
  assert.deepEqual(JSON.parse(JSON.stringify(value)), original);
});

test('economics submission nests exactly six fields and rejects incomplete declarations', () => {
  const fields = {
    cost_basis: 'MEDIA_SPEND',
    revenue_basis: 'NET_PROCEEDS',
    attribution_status: 'PARTIAL',
    spend_source: 'receipt-one',
    currency: 'USD',
    coverage_through: '2026-12-01T00:00:00Z',
  };
  const input = {
    cohort_id: 'one',
    currency: 'USD',
    ...Object.fromEntries(
      Object.entries(fields).map(([key, value]) => [`economics_${key}`, value]),
    ),
  };
  const result = JSON.parse(JSON.stringify(context.cohortPayload(input)));
  assert.deepEqual(result.economics, fields);
  assert.equal(result.currency, 'USD');
  assert.ok(!Object.keys(result).some((key) => key.startsWith('economics_')));
  assert.throws(() => context.cohortPayload({ ...input, economics_spend_source: '' }), /all six/);
  assert.equal(input.economics_cost_basis, 'MEDIA_SPEND');
});

test('optional cohort controls have labels, blank defaults, and no required legacy dependency', () => {
  const results = fs.readFileSync('mission_control/static/app-results.mjs', 'utf8');
  const section = results.slice(
    results.indexOf('function cohortEconomicsFields('),
    results.indexOf('function cohortForm('),
  );
  const c = {
    esc: (value) => String(value),
    field: (name, value, type, hint, mandatory) =>
      `<input name="${name}"${mandatory ? ' required' : ''}>`,
  };
  vm.createContext(c);
  vm.runInContext(section, c);
  const html = c.cohortEconomicsFields();
  assert.equal((html.match(/name="economics_/g) || []).length, 6);
  assert.equal((html.match(/<option value="">/g) || []).length, 3);
  assert.ok(!html.includes(' required'));
  assert.ok(html.includes('not provider verification'));
  assert.ok(html.includes('<legend>Optional acquisition economics</legend>'));
});
