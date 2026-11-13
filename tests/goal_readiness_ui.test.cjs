const { test } = require('node:test'),
  assert = require('node:assert/strict'),
  fs = require('./helpers/module-source.cjs'),
  vm = require('node:vm');
const source = fs.readFileSync(
  require('node:path').join(__dirname, '../mission_control/static/guided-workflow.mjs'),
  'utf8',
);
function fixture() {
  const state = {
      app: 'one',
      goalChoice: { app: 'one', id: 'campaign' },
      workspace: {
        app: { id: 'one', version: 1, data: {} },
        identity: { principal: 'owner' },
        access: { members: [{ principal: 'owner', role: 'OWNER', status: 'ACTIVE' }] },
        agent_access: { profiles: [] },
        social_access: { accounts: [] },
      },
    },
    calls = [],
    dialog = { open: true },
    node = { isConnected: true };
  const c = {
    state,
    globalThis: null,
    document: { querySelector: () => null },
    esc: (v) =>
      String(v ?? '')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;'),
    button: (t, a, attrs) =>
      '<button data-action="' + a + '" ' + (attrs || '') + '>' + t + '</button>',
    modal: (title, body) => calls.push({ title, body }),
    $: (s) =>
      s === '#modal'
        ? dialog
        : ['#goal-readiness-form', '#goal-readiness-mode'].includes(s)
          ? node
          : { textContent: '' },
    api: async (url, body) => {
      calls.push({ url, body });
      return {
        inventory: {
          scope_status: 'BLOCKED',
          workflows: [],
          inference: { status: 'MISSING' },
          accounts: [],
        },
        observed_at: 'test',
        inventory_sha256: 'a'.repeat(64),
      };
    },
    FormData: class {
      constructor(f) {
        this.values = f.values;
      }
      [Symbol.iterator]() {
        return Object.entries(this.values)[Symbol.iterator]();
      }
      getAll(n) {
        return this.values[n] || [];
      }
    },
    campaignOpen: () => calls.push('campaign'),
  };
  delete c.globalThis;
  vm.createContext(c);
  vm.runInContext(source, c);
  return {
    w: vm.runInContext('WMMGoalReadiness', c),
    g: vm.runInContext('WMMExceptionGuidance', c),
    state,
    calls,
    c,
    node,
    dialog,
  };
}
test('exact goal selection sends no authority fields and retains blocked broader workflows', () => {
  const h = fixture();
  const body = h.w.selection(
    {
      agent_id: 'grok-bot',
      workflows: ['social_publish', 'paid_effects'],
      agent_connection_id: 'profile',
      social_connection_ids: ['account'],
    },
    { goal: 'campaign', version: 3 },
  );
  assert.deepEqual(Object.keys(body).sort(), [
    'agent_connection_id',
    'agent_id',
    'manifest_version',
    'social_connection_ids',
    'workflows',
  ]);
  assert.equal(body.manifest_version, 3);
  assert.throws(() =>
    h.w.selection({ workflows: ['release_delivery'] }, { goal: 'campaign', version: 3 }),
  );
  assert.throws(() =>
    h.w.selection(
      { workflows: ['social_publish', 'social_publish'] },
      { goal: 'campaign', version: 3 },
    ),
  );
});
test('nonowner opens only an actionable owner setup explanation', () => {
  const h = fixture();
  h.state.workspace.access.members = [];
  h.w.open();
  assert.equal(h.calls.length, 1);
  assert.match(h.calls[0].body, /establish this app/);
  assert.equal(
    h.calls.some((x) => x.url),
    false,
  );
});
test('campaign setup offers all implemented organic channels with no effect or automatic selection', () => {
  const h = fixture();
  h.w.open();
  h.w.repair('standing-readiness');
  const html = h.calls.at(-1).body;
  assert.match(html, /value="organic_publication"/);
  for (const name of ['Instagram', 'TikTok', 'YouTube Shorts', 'LinkedIn'])
    assert.ok(html.includes(name), name);
  assert.doesNotMatch(html, /value="organic_publication" checked/);
  const body = h.w.selection(
    {
      agent_id: 'my-agent',
      workflows: ['organic_publication'],
      social_connection_ids: ['account'],
    },
    { goal: 'campaign', version: 3 },
  );
  assert.deepEqual(Array.from(body.workflows), ['organic_publication']);
  assert.equal(
    h.calls.some((x) => x.url),
    false,
  );
  assert.throws(() =>
    h.w.selection({ workflows: ['organic_publication'] }, { goal: 'research', version: 3 }),
  );
});
test('organic readiness explains exact approval and the Instagram connection path', () => {
  const h = fixture();
  const html = h.w.markup({
    inventory: {
      scope_status: 'BLOCKED',
      workflows: [
        {
          id: 'organic_publication',
          name: 'Organic publication',
          status: 'BLOCKED',
          blockers: [
            'EXACT_CURRENT_OWNER_PUBLICATION_APPROVAL_REQUIRED',
            'PUBLICATION_CONNECTION_REQUIRED',
          ],
          repair: 'Open Connections → Publish an approved post.',
        },
      ],
      inference: { status: 'TESTED_FRESH' },
      accounts: [],
    },
    observed_at: 'now',
    inventory_sha256: 'hash',
  });
  assert.match(html, /Review organic publication/);
  assert.match(html, /Instagram.*Facebook Page/);
  assert.match(html, /exact.*post/);
  assert.match(html, /No approval, grant, job or campaign/);
});
test('ready inventory never becomes active authority and source content is escaped', () => {
  const h = fixture();
  const text = h.w.markup({
    inventory: {
      scope_status: 'READY_FOR_SCOPE_REVIEW',
      workflows: [
        {
          name: '<script>',
          status: 'BLOCKED',
          blockers: ['EXACT_OWNER_CAMPAIGN_SCOPE_REQUIRED'],
          repair: '<img>',
        },
      ],
      inference: { status: 'TESTED_FRESH' },
      accounts: [],
    },
    observed_at: 'now',
    inventory_sha256: 'hash',
  });
  assert.equal(text.includes('<script>'), false);
  assert.equal(text.includes('<img>'), false);
  assert.match(text, /No approval, grant, job or campaign/);
  assert.match(text, /EXACT_OWNER_CAMPAIGN_SCOPE_REQUIRED/);
  assert.match(text, /scope review only/);
});
test('current owner submits one read-only readiness call with no expiry or spending defaults', async () => {
  const h = fixture();
  h.w.open();
  h.w.repair('standing-readiness');
  h.node.values = {
    agent_id: 'grok-bot',
    workflows: ['social_publish'],
    social_connection_ids: [],
    agent_connection_id: '',
  };
  h.node.querySelector = () => ({ disabled: false });
  await h.w.submit(h.node);
  const call = h.calls.find((x) => x.url);
  assert.equal(call.url, '/api/apps/one/agent-grants/automation-readiness');
  assert.equal(Object.hasOwn(call.body, 'limits'), false);
  assert.equal(Object.hasOwn(call.body, 'purpose'), false);
  assert.match(h.calls.at(-1).body, /No approval/);
});
test('app/version/principal/goal changes or replaced dialog discard late readback', async () => {
  for (const kind of ['app', 'version', 'principal', 'goal', 'dialog', 'replaced']) {
    const h = fixture();
    h.w.open();
    h.w.repair('standing-readiness');
    h.node.values = {
      agent_id: 'my-agent',
      workflows: ['social_publish'],
      social_connection_ids: [],
    };
    h.node.querySelector = () => ({ disabled: false });
    h.c.api = async () => {
      if (kind === 'app') h.state.app = 'two';
      if (kind === 'version') h.state.workspace.app.version = 2;
      if (kind === 'principal') h.state.workspace.identity.principal = 'other';
      if (kind === 'goal') h.state.goalChoice.id = 'research';
      if (kind === 'dialog') h.dialog.open = false;
      if (kind === 'replaced') h.node.isConnected = false;
      return { inventory: {} };
    };
    await h.w.submit(h.node);
    assert.equal(h.calls.length, 2, kind);
  }
});
test('unknown repair routes reject without a call', () => {
  const h = fixture();
  assert.throws(() => h.w.repair('http://external'));
  assert.equal(h.calls.length, 0);
});
test('mode choice starts no calls and personal agent opens only existing grant controls', () => {
  const h = fixture();
  h.c.WMMAgentControl = {
    action: (node, services) => h.calls.push({ grant: node.dataset.action, services }),
  };
  h.c.growthReviewServices = () => ({ current: true });
  h.w.open();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].title, 'Choose your agent setup');
  assert.match(h.calls[0].body, /goal-readiness-mode/);
  assert.match(h.calls[0].body, /Use my personal agent/);
  assert.match(h.calls[0].body, /Check WMM-managed setup/);
  assert.match(h.calls[0].body, /This step starts no work and grants no permission/);
  h.w.repair('external-agent');
  assert.equal(h.calls[1].grant, 'control-grants');
  assert.equal(
    h.calls.some((x) => x.url),
    false,
  );
  assert.throws(() => h.w.repair('standing-readiness'));
});
test('stale or closed initial mode cannot route either execution mode', () => {
  for (const tool of ['external-agent', 'standing-readiness'])
    for (const kind of ['app', 'version', 'principal', 'goal', 'dialog', 'replaced']) {
      const h = fixture();
      h.w.open();
      if (kind === 'app') h.state.app = 'two';
      if (kind === 'version') h.state.workspace.app.version = 2;
      if (kind === 'principal') h.state.workspace.identity.principal = 'other';
      if (kind === 'goal') h.state.goalChoice.id = 'research';
      if (kind === 'dialog') h.dialog.open = false;
      if (kind === 'replaced') h.node.isConnected = false;
      assert.throws(() => h.w.repair(tool));
      assert.equal(h.calls.length, 1);
    }
});
test('the backend STALE state explains that verification needs refreshing', () => {
  const h = fixture();
  const text = h.w.markup({
    inventory: {
      scope_status: 'BLOCKED',
      workflows: [],
      inference: { status: 'STALE' },
      accounts: [],
    },
    observed_at: 'now',
    inventory_sha256: 'hash',
  });
  assert.match(text, /Agent connection: Verification needs refreshing/);
  assert.match(text, /agent: STALE/);
});
test('inherited and unknown diagnostic keys use review guidance while preserving escaped details', () => {
  for (const key of ['constructor', '__proto__', 'toString', 'NEW_UNKNOWN_STATUS', '<img>']) {
    const h = fixture();
    const text = h.w.markup({
      inventory: {
        scope_status: key,
        workflows: [{ id: key, name: 'Saved workflow', status: key, blockers: [key] }],
        inference: { status: key },
        accounts: [],
      },
      observed_at: 'now',
      inventory_sha256: 'hash',
    });
    assert.match(text, /<h3>Needs review<\/h3>/);
    assert.match(text, /<strong>Saved workflow<\/strong>: Needs review/);
    assert.match(text, /Open Connections to inspect the selected agent and accounts/);
    assert.equal(text.includes('[native code]'), false);
    assert.equal(text.includes('[object Object]'), false);
    assert.equal(text.includes('<img>'), false);
    assert.match(text, /<details><summary>Technical details<\/summary>/);
  }
});

test('exception guidance translates supported recovery states without overclaiming', () => {
  const h = fixture(),
    g = h.g;
  for (const [state, headline, tool] of [
    ['UNKNOWN', 'Delivery is unconfirmed', 'campaign'],
    ['CANCEL_REQUESTED', 'New local work stopped', 'campaign'],
    ['BLOCKED', 'Work is paused', 'connections'],
    ['WAITING_FOR_REPORTS', 'Report rows are not available yet', 'connections'],
    ['EXPIRED', 'Permission or connection expired', 'connections'],
    ['EXHAUSTED', 'Approved check limit reached', 'agreement'],
  ]) {
    const row = g.normalize({ state, evidence_refs: ['receipt-1'] });
    assert.equal(row.headline, headline, state);
    assert.equal(row.tool, tool, state);
    assert.deepEqual(row.evidence_refs, ['receipt-1']);
  }
  const unknown = g.normalize({ state: 'PROVIDER_SURPRISE', reason: '<unsafe>' });
  assert.equal(unknown.headline, 'Work needs review');
  assert.equal(unknown.reason, '<unsafe>');
  assert.equal(unknown.tool, 'agreement');
});
test('exception panel keeps evidence escaped and renders no panel for absent states', () => {
  const h = fixture(),
    g = h.g;
  assert.equal(g.panel([]), '');
  const html = g.panel([
    {
      state: 'WAITING_FOR_REPORTS',
      evidence_refs: ['<receipt>'],
      source: 'App Store Connect',
      observed_at: '2026-11-05T00:00:00Z',
      next_due: '2026-11-06T00:00:00Z',
      repair_route: 'connections',
    },
  ]);
  assert.match(html, /Workflow updates/);
  assert.match(html, /Report rows are not available yet/);
  assert.match(html, /This does not mean zero activity/);
  assert.match(html, /&lt;receipt&gt;/);
  assert.equal(html.includes('<receipt>'), false);
  assert.match(html, /Observed: 2026-11-05/);
  assert.match(html, /next due 2026-11-06/);
  assert.match(html, /Source: App Store Connect/);
  assert.match(html, /data-tool="connections"/);
});

test('missing Facebook credential replaces the historical verified label with a repair', () => {
  const { w } = fixture();
  const data = {
    inventory: {
      scope_status: 'READY_FOR_SCOPE_REVIEW',
      workflows: [],
      inference: { status: 'MISSING' },
      accounts: [{ id: 'a', provider: 'facebook', destination_id: 'page', status: 'TESTED_FRESH' }],
    },
    observed_at: 'now',
    inventory_sha256: 'hash',
  };
  const reconnect = w.markup({ ...data, credential_repairs: { a: 'RECONNECT_REQUIRED' } });
  assert.match(reconnect, /<h3>Needs setup<\/h3>/);
  assert.match(reconnect, /facebook \/ page · Reconnect Facebook in Connections/);
  assert.doesNotMatch(reconnect, /Recently verified/);
  assert.match(
    w.markup({ ...data, credential_repairs: { a: 'PROTECTED_STORAGE_UNAVAILABLE' } }),
    /Unlock this device’s protected credential storage/,
  );
  assert.match(w.markup(data), /Recently verified/);
});

test('next scheduled check remains visible without a prior observation', () => {
  const h = fixture();
  const html = h.g.panel([{ state: 'WAITING_FOR_REPORTS', next_due: '2026-11-14T10:00:00Z' }]);
  assert.match(html, /next due 2026-11-14T10:00:00Z/);
  assert.doesNotMatch(html, /Observed:/);
});
