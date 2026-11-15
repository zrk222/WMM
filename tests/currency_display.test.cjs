const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');

test('browser profiles exactly match the frozen Python authority', async () => {
  const { CURRENCY_DIGITS } = await import('../mission_control/static/currency-profile.mjs');
  const expected = JSON.parse(
    execFileSync(
      'python',
      [
        '-c',
        'import json; from mission_control.currency_units import CURRENCY_DIGITS; print(json.dumps(CURRENCY_DIGITS))',
      ],
      { encoding: 'utf8' },
    ),
  );
  assert.deepEqual(CURRENCY_DIGITS, expected);
});

test('actual formatter keeps currency exponents, bounds and fractional minor estimates', async () => {
  const { money } = await import('../mission_control/static/app-money.mjs');
  for (const [code, major, digits] of [
    ['USD', 12.34, 2],
    ['JPY', 1234, 0],
    ['KWD', 1.234, 3],
    ['CLF', 0.1234, 4],
  ]) {
    for (const sign of [0, 1, -1]) {
      const expected = new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: code,
        currencyDisplay: 'code',
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(major * sign);
      assert.equal(money(1234 * sign, code, 'en-US'), expected);
    }
  }
  assert.equal(money(0.5, 'USD', 'en-US'), 'USD\u00a00.005');
  assert.equal(money(1.25, 'JPY', 'en-US'), 'JPY\u00a01.25');
});

test('unknown metadata retains raw units and invalid values never become cash', async () => {
  const { money } = await import('../mission_control/static/app-money.mjs');
  for (const code of [
    null,
    undefined,
    '',
    'ZZZ',
    'usd',
    '<img src=x onerror=alert(1)>',
    '__proto__',
  ]) {
    assert.equal(money(1234, code), '1234 minor units (currency unavailable)');
  }
  for (const value of [null, undefined, NaN, Infinity, -Infinity, '1234', true, {}, []]) {
    assert.equal(money(value, 'USD'), 'Unavailable');
  }
});

test('tiny positive and negative estimates never render as a measured zero', async () => {
  const { money } = await import('../mission_control/static/app-money.mjs');
  for (const code of ['USD', 'JPY', 'KWD', 'CLF']) {
    for (const value of [0.0000001, -0.0000001, Number.MIN_VALUE, -Number.MIN_VALUE]) {
      assert.equal(
        money(value, code, 'en-US'),
        `${value} minor units (${code}; fractional estimate)`,
      );
    }
  }
  assert.equal(money(0, 'USD', 'en-US'), 'USD\u00a00.00');
});
