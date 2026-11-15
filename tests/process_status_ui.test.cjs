const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../mission_control/static/app.mjs'), 'utf8');
const helpers = source.slice(source.indexOf('const esc ='), source.indexOf('const notice ='));
const renderStatus = vm.runInNewContext(`${helpers}; status`);
const css = readFileSync(join(__dirname, '../mission_control/static/style.css'), 'utf8');
const rules = [...css.matchAll(/\.status:is\(([^)]+)\)\s*\{([^}]+)\}/g)];

function palette(state) {
  return rules.find(([_, selectors]) =>
    selectors
      .split(',')
      .map((s) => s.trim())
      .includes(`.${state}`),
  )?.[2];
}

test('real job and worker states retain their exact readable labels with a color class', () => {
  for (const state of [
    'RUNNING',
    'STARTING',
    'STOPPING',
    'RECOVERING',
    'QUEUED',
    'WAITING_REVIEW',
    'RETRY_WAIT',
    'CANCEL_REQUESTED',
    'WAITING_FOR_REPORTS',
    'NEEDS_RECONCILIATION',
    'SUCCEEDED',
    'FAILED',
    'BLOCKED',
    'STOPPED',
    'PAUSED',
    'CANCELLED',
  ]) {
    const html = renderStatus(state);
    assert.match(html, new RegExp(`class="status ${state.toLowerCase()}"`));
    assert.ok(html.includes(state.replaceAll('_', ' ')), `${state} label was changed`);
    assert.ok(palette(state.toLowerCase()), `${state} has no deliberate state palette`);
  }
});

test('running, queued, failed, succeeded and stopped remain five distinct semantic states', () => {
  const color = (state) => palette(state).match(/--process-ink:\s*(#[a-f0-9]+)/)[1];
  assert.equal(new Set(['running', 'queued', 'failed', 'succeeded', 'stopped'].map(color)).size, 5);
  assert.equal(color('queued'), color('waiting_for_reports'));
  assert.equal(color('blocked'), color('needs_reconciliation'));
  assert.equal(color('active'), color('running'));
  assert.notEqual(color('active'), color('succeeded'));
  assert.equal(color('cancelled'), color('stopped'));
});

test('a blocked job is attention, not a failed job; unknown states cannot look like success', () => {
  assert.notEqual(palette('blocked'), palette('failed'));
  assert.notEqual(palette('unknown'), palette('succeeded'));
  assert.equal(palette('unrecognized_state'), undefined);
  assert.match(renderStatus('UNRECOGNIZED_STATE'), />UNRECOGNIZED STATE<\/span>/);
  const escaped = renderStatus('<img src=x onerror="alert(1)">');
  assert.ok(!escaped.includes('<img'));
  assert.ok(escaped.includes('&lt;img'));
});

test('the shared status marker is static, carries no replacement words and wraps on narrow screens', () => {
  const dot = css.match(/\.status::before\s*\{([^}]+)\}/)?.[1];
  assert.match(dot, /content:\s*''/);
  assert.doesNotMatch(dot, /animation|transition/);
  const base = css.match(/\/\* Process colors[\s\S]+?\.status\[class\]\s*\{([^}]+)\}/)?.[1];
  assert.match(base, /white-space:\s*normal/);
  assert.match(base, /overflow-wrap:\s*anywhere/);
});
