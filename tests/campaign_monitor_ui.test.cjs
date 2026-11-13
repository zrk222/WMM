const { test } = require('node:test'),
  assert = require('node:assert/strict'),
  fs = require('./helpers/module-source.cjs'),
  vm = require('node:vm'),
  path = require('node:path');
const source = fs.readFileSync(
  path.join(__dirname, '../mission_control/static/campaign-monitor.mjs'),
  'utf8',
);
function fixture() {
  const nodes = new Map(),
    calls = [],
    c = {
      Date,
      state: { app: 'one', workspace: { app: { version: 1 }, identity: { principal: 'owner' } } },
      esc: (x) => String(x ?? '').replaceAll('<', '&lt;'),
      button: () => '',
      FormData: class {
        constructor(form) {
          return Object.assign(Object.entries(form.values || {}), {
            getAll: () => form.targets || [],
          });
        }
      },
    };
  nodes.set('#modal', { open: true, isConnected: true });
  c.$ = (x) => nodes.get(x);
  c.modal = (title, html) => {
    for (const [key, node] of nodes) if (key !== '#modal') node.isConnected = false;
    for (const m of html.matchAll(/id="([^"]+)"/g))
      nodes.set('#' + m[1], {
        isConnected: true,
        textContent: '',
        querySelector: () => ({ disabled: false }),
      });
    calls.push({ title, html });
  };
  c.api = async () => ({ scopes: [], monitors: [] });
  vm.createContext(c);
  vm.runInContext(source, c);
  return { a: vm.runInContext('WMMCampaignMonitor', c), c, nodes, calls };
}
const scope = { scope_id: 's', status: 'ACTIVE', expires_at: '2026-11-03T00:00:00Z' },
  rows = [{ id: 'i', scope_id: 's', request_hash: 'h', kind: 'AD' }],
  values = {
    cadence_seconds: '300',
    max_runs: '10',
    max_provider_units: '80',
    max_pause_attempts: '0',
    expires_at: '2026-11-02T23:00:00Z',
  },
  clock = Date.parse('2026-11-02T20:00:00Z');
test('exact monitor targets and finite limits issue no client authority', () => {
  const h = fixture(),
    p = h.a.proposal(values, rows, scope, clock);
  assert.equal(p.targets[0].intent_id, 'i');
  assert.equal(p.targets[0].request_hash, 'h');
  assert.deepEqual(Array.from(p.protective_conditions), []);
  assert.equal(h.calls.length, 0);
  for (const bad of [
    { ...values, cadence_seconds: '29' },
    { ...values, max_runs: '101' },
    { ...values, max_provider_units: '161' },
    { ...values, max_pause_attempts: '1' },
    { ...values, configuration_drift: 'on' },
    { ...values, expires_at: '2026-11-04T00:00:00Z' },
  ])
    assert.throws(() => h.a.proposal(bad, rows, scope, clock));
  assert.throws(() => h.a.proposal(values, [], scope, clock));
});
test('protective rules are explicit and saved target selector stays in scope', () => {
  const h = fixture(),
    p = h.a.proposal(
      { ...values, max_pause_attempts: '1', configuration_drift: 'on' },
      rows,
      scope,
      clock,
    );
  assert.deepEqual(Array.from(p.protective_conditions), ['configuration_drift']);
  assert.equal(
    h.a.options({
      scope,
      intents: [
        ...rows,
        { id: 'other', scope_id: 'other', request_hash: 'h' },
        { id: 'nohash', scope_id: 's' },
      ],
    }).length,
    1,
  );
});
test('late monitor history after app owner version or modal changes is ignored', async () => {
  for (const change of [
    (h) => (h.c.state.app = 'two'),
    (h) => h.c.state.workspace.app.version++,
    (h) => (h.c.state.workspace.identity.principal = 'other'),
    (h) => h.c.modal('other', '<div id="other"></div>'),
    (h) => (h.nodes.get('#modal').open = false),
  ]) {
    const h = fixture(),
      pending = [];
    h.c.api = () => new Promise((r) => pending.push(r));
    const opened = h.a.open();
    change(h);
    pending.forEach((r) => r({ scopes: [], monitors: [] }));
    await opened;
    assert.equal(h.nodes.has('#monitor-home'), false);
  }
});
test('monitor report omits private source and raw provider payloads', () => {
  const h = fixture(),
    data = {
      id: 'monitor',
      effective_status: 'BLOCKED',
      summary_hash: 'hash',
      summary: {
        proposal: {
          scope_id: 's',
          targets: [{ intent_id: 'i', request_hash: 'h' }],
          expires_at: 'later',
        },
        private_key: 'SECRET',
      },
      runs: 1,
      provider_units: 8,
      pause_attempts: 1,
      last_observation: { job_id: 'job', status: 'BLOCKED', raw: 'SECRET_COPY' },
    };
  const report = h.a.report(data, {}),
    text = JSON.stringify(report);
  assert.doesNotMatch(text, /SECRET/);
  assert.match(text, /BLOCKED/);
  assert.match(text, /exact|Exact/);
});
test('saved progress exposes unknown delivery and does not equate OFF with paused ads', () => {
  const h = fixture(),
    data = {
      effective_status: 'BLOCKED',
      summary_hash: 'hash',
      summary: {
        proposal: {
          scope_id: 's',
          targets: rows.map((r) => ({ intent_id: r.id, request_hash: r.request_hash })),
          cadence_seconds: 300,
          expires_at: 'later',
          max_runs: 10,
          max_provider_units: 80,
          max_pause_attempts: 1,
          protective_conditions: ['configuration_drift'],
        },
      },
      runs: 1,
      provider_units: 8,
      pause_attempts: 1,
      last_observation: {
        job_id: 'job',
        status: 'BLOCKED',
        updated: 'now',
        external_execution: 'MONITOR_INTERRUPTED_UNCONFIRMED',
        observations: [{ intent_id: 'i', status: 'UNKNOWN' }],
      },
    };
  const html = h.a.progress(data);
  assert.match(html, /UNKNOWN/);
  assert.match(html, /does not pause an already running ad/);
  assert.match(html, /Provider units reserved/);
  assert.match(html, /stopped before it could confirm the provider result/);
  assert.match(
    JSON.stringify(h.a.report(data, {})),
    /provider result unconfirmed after worker interruption/,
  );
});

test('late monitor inspection is single flight and cannot reopen a closed dialog', async () => {
  const h = fixture();
  await h.a.open();
  let resolve,
    count = 0;
  h.c.api = () => {
    count++;
    return new Promise((r) => (resolve = r));
  };
  const first = h.a.inspect('monitor');
  await h.a.inspect('monitor');
  assert.equal(count, 1);
  h.nodes.get('#modal').open = false;
  resolve({});
  await first;
  assert.equal(h.nodes.has('#monitor-progress'), false);
});

test('unreadable monitor evidence remains inspectable from history and exports a sanitized repair report', async () => {
  const h = fixture();
  const data = {
    id: 'repair-monitor',
    status: 'BLOCKED',
    effective_status: 'NEEDS_REPAIR',
    evidence_unavailable: true,
    summary: null,
    summary_hash: null,
    runs: 1,
    provider_units: 2,
    pause_attempts: 0,
    repair: 'SECRET_RAW_REPAIR',
    last_observation: { raw: 'SECRET_PROVIDER' },
  };
  h.c.api = async (url) =>
    url.endsWith('/campaign-monitor/history')
      ? { monitors: [data] }
      : url.endsWith('/campaigns/history')
        ? { scopes: [] }
        : data;
  await h.a.open();
  assert.match(h.calls.at(-1).html, /NEEDS_REPAIR/);
  await h.a.inspect(data.id);
  const html = h.calls.at(-1).html;
  assert.ok(h.nodes.has('#monitor-progress'));
  assert.match(html, /evidence is unavailable/);
  assert.doesNotMatch(html, /SECRET|approved worker checks|No completed monitoring observation/);
  const report = JSON.stringify(h.a.report(data, {}));
  assert.match(report, /NEEDS_REPAIR/);
  assert.match(report, /evidence is unavailable/);
  assert.doesNotMatch(report, /SECRET|Scope undefined|Exact target IDs|summary null/);
});

test('OFF monitor with unreadable evidence stays OFF in inspection and report', async () => {
  const h = fixture();
  const data = {
    id: 'off-monitor',
    status: 'OFF',
    effective_status: 'OFF',
    evidence_unavailable: true,
    summary: null,
    summary_hash: null,
    runs: 1,
    provider_units: 2,
    pause_attempts: 0,
  };
  h.c.api = async () => data;
  await h.a.inspect(data.id);
  const html = h.calls.at(-1).html;
  assert.ok(h.nodes.has('#monitor-progress'));
  assert.match(html, /Monitoring off/);
  assert.match(html, /Future monitoring is stopped/);
  assert.match(html, /evidence is unavailable/);
  const report = h.a.report(data, {});
  assert.equal(report.metrics[0].value, 'OFF');
  assert.doesNotMatch(JSON.stringify(report), /NEEDS_REPAIR|Exact target IDs/);
});
