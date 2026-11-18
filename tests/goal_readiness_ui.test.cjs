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
    node = { isConnected: true },
    messages = { status: { textContent: '' }, error: { textContent: '' } };
  const c = {
    state,
    globalThis: null,
    document: { querySelector: () => null },
    esc: (v) =>
      String(v ?? '')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;'),
    button: (t, a, attrs, style) =>
      '<button class="' +
      (style || '') +
      '" data-action="' +
      a +
      '" ' +
      (attrs || '') +
      '>' +
      t +
      '</button>',
    modal: (title, body) => calls.push({ title, body }),
    $: (s) =>
      s === '#modal'
        ? dialog
        : ['#goal-readiness-form', '#goal-readiness-mode'].includes(s)
          ? node
          : s === '#goal-readiness-status'
            ? messages.status
            : messages.error,
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
    messages,
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
test('each local readiness route needs neither owner nor agent setup', () => {
  for (const [goal, view, anchor] of [
    ['research', 'evidence', '#creative-source-library-heading'],
    ['creative', 'research', '#creative-rendering-heading'],
    ['measurement', 'results', '#analytics-overview-heading'],
  ]) {
    const h = fixture();
    h.state.goalChoice.id = goal;
    h.state.workspace.access.members = [];
    h.c.guidedNavigate = (...args) => h.calls.push(args);
    h.w.open();
    assert.deepEqual(h.calls, [[view, anchor]]);

    h.w.open('managed');
    assert.match(h.calls[1].body, /establish this app/);
    assert.doesNotMatch(h.calls[1].body, /goal-readiness-form/);
    h.state.app = 'other';
    assert.throws(() => h.w.open(), /selected app to finish loading/);
    assert.equal(h.calls.length, 2);
  }
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
test('app/version/principal/role/goal changes or replaced dialog discard late readback', async () => {
  for (const kind of ['app', 'version', 'principal', 'role', 'goal', 'dialog', 'replaced']) {
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
      if (kind === 'role') h.state.workspace.access.members[0].status = 'REVOKED';
      if (kind === 'goal') h.state.goalChoice.id = 'research';
      if (kind === 'dialog') h.dialog.open = false;
      if (kind === 'replaced') h.node.isConnected = false;
      return { inventory: {} };
    };
    await h.w.submit(h.node);
    assert.equal(h.calls.length, 2, kind);
  }
});
test('editing the account during a pending check preserves the new selection and a clean retry', async () => {
  for (const failed of [false, true]) {
    const h = fixture();
    h.w.open();
    h.w.repair('standing-readiness');
    h.node.values = {
      agent_id: 'my-agent',
      workflows: ['social_publish'],
      social_connection_ids: ['old'],
    };
    const control = { disabled: false };
    h.node.querySelector = () => control;
    let complete;
    const original = h.c.api;
    h.c.api = async (_, body) => {
      assert.deepEqual(Array.from(body.social_connection_ids), ['old']);
      return new Promise((resolve, reject) => {
        complete = () =>
          failed ? reject(new Error('Old connection error')) : resolve({ inventory: {} });
      });
    };
    const pending = h.w.submit(h.node);
    assert.equal(control.disabled, true);
    assert.match(h.messages.status.textContent, /Checking/);
    h.node.values.social_connection_ids = ['new'];
    await h.w.submit(h.node);
    complete();
    await pending;
    assert.equal(h.calls.length, 2);
    assert.equal(control.disabled, false);
    assert.equal(h.messages.status.textContent, '');
    assert.match(h.messages.error.textContent, /Your selection changed/);
    h.c.api = original;
    await h.w.submit(h.node);
    assert.deepEqual(Array.from(h.calls.at(-2).body.social_connection_ids), ['new']);
    assert.equal(h.messages.error.textContent, '');
    assert.match(h.calls.at(-1).body, /No approval/);
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
  assert.equal(h.calls[0].title, 'Check campaign connections');
  assert.match(h.calls[0].body, /goal-readiness-mode/);
  assert.match(h.calls[0].body, /Use my personal agent/);
  assert.match(h.calls[0].body, /Check WMM-managed setup/);
  assert.match(h.calls[0].body, /Check Facebook and Meta accounts/);
  assert.match(h.calls[0].body, /This step starts no work and grants no permission/);
  h.w.repair('external-agent');
  assert.equal(h.calls[1].grant, 'control-grants');
  assert.equal(
    h.calls.some((x) => x.url),
    false,
  );
  assert.throws(() => h.w.repair('standing-readiness'));
});
test('stale or closed initial setup cannot route its controls', () => {
  for (const tool of ['campaign-accounts', 'external-agent', 'standing-readiness'])
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
    ['APPLE_CAMPAIGN_FILE_AVAILABLE', 'Apple lists a daily download report', 'apple-analytics'],
    ['APPLE_REPORT_SETUP_REQUIRED', 'Apple reporting needs setup', 'apple-analytics'],
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

test('delivery uncertainty comes first while only a verified future Apple wait is folded', () => {
  const { g } = fixture();
  const watch = {
    state: 'WAITING_FOR_REPORTS',
    source: 'App Store Connect',
    repair_route: 'apple-analytics',
    monitoring: true,
  };
  const rows = [
    watch,
    { state: 'BLOCKED', reason: 'Repair an ordinary blocker.' },
    { state: 'CAMPAIGN_MONITOR_PAUSE_UNAVAILABLE' },
    { state: 'FUTURE_UNKNOWN_STATE', monitoring: true, reason: 'Keep this uncertainty visible.' },
  ];
  const html = g.panel(rows);
  assert.match(html, /3 items need review/);
  assert.ok(
    html.indexOf('Protective pause is unavailable') < html.indexOf('Repair an ordinary blocker'),
  );
  assert.ok(
    html.indexOf('Keep this uncertainty visible') < html.indexOf('<summary>Monitoring · 1'),
  );
  assert.ok(
    html.indexOf('<summary>Monitoring · 1') < html.indexOf('Report rows are not available yet'),
  );
  assert.doesNotMatch(g.panel([watch]), /<details>/);
  for (const row of [
    { ...watch, monitoring: false },
    { ...watch, source: 'Another provider' },
    { ...watch, repair_route: 'connections' },
  ]) {
    assert.equal(g.normalize(row).attention, 'review');
  }
});

test('campaign warning opens only the exact saved schedule for review', () => {
  const { g } = fixture();
  const batch = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  const row = {
    state: 'CAMPAIGN_SCHEDULE_NEEDS_RECONCILIATION',
    repair_route: 'campaign-schedule',
    batch_id: batch,
    reason: 'Delivery is unconfirmed.',
    next_action: 'Check provider status before retrying.',
  };
  const html = g.panel([row]);
  assert.match(html, /Check whether scheduled work went live/);
  assert.match(html, /Check provider status before retrying/);
  assert.match(html, /data-action="campaign-schedule-status"/);
  assert.match(html, new RegExp('data-batch="' + batch + '"'));
  assert.doesNotMatch(html, /data-action="campaign-schedule-(activate|off)"/);
  for (const wrong of [
    { batch_id: '"><script>' },
    { repair_route: 'unknown' },
    { state: 'UNKNOWN' },
  ]) {
    assert.doesNotMatch(g.panel([{ ...row, ...wrong }]), /data-batch=|<script>/);
  }
});

test('monitor warning opens only an exact saved monitor and never a mutation', () => {
  const { g } = fixture();
  const id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  const row = {
    state: 'CAMPAIGN_MONITOR_NEEDS_RECONCILIATION',
    repair_route: 'campaign-monitor',
    monitor_id: id,
    next_action: 'Check the saved receipt before assuming the campaign paused.',
  };
  const html = g.panel([row]);
  assert.match(html, /Check the last monitoring result/);
  assert.match(html, /before assuming the campaign paused/);
  assert.match(html, new RegExp('data-action="campaign-monitor-status" data-id="' + id + '"'));
  assert.doesNotMatch(html, /data-action="campaign-monitor-(activate|off)"/);
  for (const change of [
    { monitor_id: '<script>' },
    { repair_route: 'unknown' },
    { state: 'CAMPAIGN_MONITOR_UNKNOWN' },
  ]) {
    assert.doesNotMatch(g.panel([{ ...row, ...change }]), /campaign-monitor-status|<script>/);
  }
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
  assert.match(reconnect, /class="primary" data-action="goal-repair" data-tool="social-accounts"/);
  assert.equal(reconnect.match(/data-tool="social-accounts"/g).length, 1);
  assert.doesNotMatch(reconnect, /Recently verified/);
  assert.match(
    w.markup({ ...data, credential_repairs: { a: 'PROTECTED_STORAGE_UNAVAILABLE' } }),
    /Unlock this device’s protected credential storage/,
  );
  assert.match(w.markup(data), /Recently verified/);
  assert.match(
    w.markup(data),
    /class="primary" data-action="goal-repair" data-tool="combined-agreement"/,
  );
});

test('creative readiness opens the local video tools with focus and does not start work', () => {
  const h = fixture();
  const markup = h.w.markup({
    inventory: {
      scope_status: 'BLOCKED',
      workflows: [
        {
          id: 'hypit_caption_render',
          name: 'Local Hypit caption composition',
          status: 'BLOCKED',
          blockers: ['LOCAL_MEDIA_RUNTIME_VERIFICATION_REQUIRED'],
        },
      ],
      inference: { status: 'TESTED_FRESH' },
      accounts: [],
    },
    observed_at: 'now',
    inventory_sha256: 'hash',
  });
  assert.match(
    markup,
    /class="primary" data-action="goal-repair" data-tool="video-tools">Review local video tools/,
  );
  assert.match(markup, /Verify the local video tools before rendering/);
  assert.match(markup, /Technical details.*LOCAL_MEDIA_RUNTIME_VERIFICATION_REQUIRED/s);
  const rendering = fs.readFileSync(
    require('node:path').join(__dirname, '../mission_control/static/creative-rendering.mjs'),
    'utf8',
  );
  assert.match(rendering, /<h2 id="creative-rendering-heading" tabindex="-1">/);
  let anchor = '';
  const navigation = [];
  h.dialog.close = () => navigation.push('close');
  h.c.$ = (selector) => (selector === '#modal' ? h.dialog : { replaceChildren() {} });
  h.c.render = () => navigation.push(h.state.view);
  h.c.document.querySelector = (selector) => {
    anchor = selector;
    return {
      scrollIntoView: () => navigation.push('scroll'),
      focus: () => navigation.push('focus'),
    };
  };
  h.w.repair('video-tools');
  assert.equal(anchor, '#creative-rendering-heading');
  assert.deepEqual(navigation, ['close', 'research', 'scroll', 'focus']);
  assert.deepEqual(h.calls, []);
});

test('next scheduled check remains visible without a prior observation', () => {
  const h = fixture();
  const html = h.g.panel([{ state: 'WAITING_FOR_REPORTS', next_due: '2026-11-14T10:00:00Z' }]);
  assert.match(html, /next due 2026-11-14T10:00:00Z/);
  assert.doesNotMatch(html, /Observed:/);
});

test('empty campaign destinations offer the exact social setup and combined review', () => {
  const h = fixture();
  h.c.guidedNavigate = (view, anchor) => h.calls.push({ view, anchor });
  vm.runInContext('WMMAgreement.open = () => modal("Combined agreement", "")', h.c);
  h.w.open();
  h.w.repair('standing-readiness');
  assert.match(h.calls.at(-1).body, /No social destination is connected for this app/);
  assert.match(h.calls.at(-1).body, /data-tool="social-accounts"/);
  h.w.repair('social-accounts');
  assert.deepEqual(h.calls.at(-1), { view: 'connections', anchor: '#social-heading' });
  h.w.repair('combined-agreement');
  assert.equal(h.calls.at(-1).title, 'Combined agreement');
  assert.equal(
    h.calls.some((item) => item.url),
    false,
  );
});

test('current campaign packet opens only a matched upstream input and leaves saved views read-only', () => {
  const h = fixture();
  const diagnostics = [
    [3, 'measurement', 'Add current measurement evidence'],
    [4, 'cohort', 'Add current cohort evidence', [3]],
    [6, 'findings', 'Add current experiment evidence'],
    [7, 'distribution', null, [4, 6]],
  ];
  h.state.workspace.workflow = {
    steps: diagnostics.map(([id, tool, need, dependencies]) => ({
      id,
      title: tool,
      local_status: 'NEEDS_INPUT',
      direct_needs: need ? [need] : [],
      dependency_needs: (dependencies || []).map((parent) => 'Finish stage ' + parent + ': input'),
      critical_findings: id === 6 ? ['Confirmed broken signup'] : [],
      primary_need: id === 6 ? 'Resolve critical finding: Confirmed broken signup' : need,
      primary: { id: tool, title: tool },
    })),
  };
  h.state.workspace.preparation = {
    source_hash: 'exact',
    outputs: [{ stage: 7, status: 'BLOCKED', packet: { title: 'Campaign' }, missing: [] }],
  };
  h.c.notice = h.c.esc;
  h.c.json = (v) => h.c.esc(JSON.stringify(v));
  h.c.document.addEventListener = () => {};
  const preparation = fs.readFileSync('mission_control/static/automatic-preparation.mjs', 'utf8');
  vm.runInContext(preparation, h.c);
  h.c.guidedOpenTool = (id) => h.calls.push(id);
  const packet = vm.runInContext('WMMGoalPacket', h.c);
  const model = packet.model();
  assert.doesNotMatch(packet.view(model), /automatic-goal-repair/);
  const current = packet.view(model, true);
  assert.match(current, /What needs attention first/);
  assert.match(current, /Connect measurement/);
  assert.match(current, /Other inputs to review/);
  assert.match(
    current,
    /Resolve critical finding: Confirmed broken signup<\/p><button[^>]+data-tool="findings"/,
  );
  assert.doesNotMatch(current, /Add current experiment evidence/);
  assert.match(current, /observational-campaign-open/);
  const node = {
    dataset: {
      app: 'one',
      version: '1',
      goal: 'campaign',
      sourceHash: 'exact',
      action: 'automatic-goal-repair',
      stage: '3',
      tool: 'measurement',
    },
  };
  packet.action(node);
  assert.deepEqual(h.calls, ['measurement']);
  node.dataset.tool = 'experiment';
  assert.throws(() => packet.action(node), /inputs changed/i);
  node.dataset.tool = 'measurement';
  node.dataset.sourceHash = 'old';
  assert.throws(() => packet.action(node), /evidence changed/i);
  assert.deepEqual(h.calls, ['measurement']);

  const historical = { ...model, source_hash: 'previous', created_at: 'then' };
  h.state.workspace.jobs = [
    {
      id: 'saved-run',
      app_id: 'one',
      action: 'pipeline',
      status: 'SUCCEEDED',
      created: 'then',
      data: { goal_packet: { goal: 'campaign', manifest_version: 1, source_hash: 'previous' } },
      result: { goal_packet: historical },
    },
  ];
  Object.assign(node.dataset, {
    action: 'automatic-goal-reopen',
    sourceHash: 'exact',
    job: 'saved-run',
  });
  packet.action(node);
  const saved = h.calls.at(-1).body;
  assert.match(saved, /Historical snapshot/);
  assert.match(saved, /Open current packet/);
  assert.doesNotMatch(saved, /observational-campaign-open|automatic-goal-repair/);
});

test('verified Apple report wait navigates to the exact panel without any read or reconnect', () => {
  const h = fixture();
  const row = {
    state: 'WAITING_FOR_REPORTS',
    source: 'App Store Connect',
    repair_route: 'apple-analytics',
  };
  h.state.workspace.workflow = { exceptions: [row] };
  const navigations = [];
  h.c.guidedNavigate = (...args) => navigations.push(args);
  const action = vm.runInContext('goalAction', h.c);
  const node = {
    isConnected: true,
    dataset: { action: 'goal-apple-report-availability', app: 'one', version: '1' },
  };
  assert.match(
    h.g.panel([row]),
    /data-action="goal-apple-report-availability" data-app="one" data-version="1">Review Apple report availability/,
  );
  action(node);
  assert.deepEqual(navigations, [['connections', '#apple-report-availability-heading']]);
  action({ ...node, isConnected: false });
  h.state.app = 'two';
  action(node);
  h.state.app = 'one';
  h.state.workspace.app.version = 2;
  action(node);
  h.state.workspace.app.version = 1;
  h.state.workspace.workflow.exceptions = [{ ...row, source: 'other' }];
  action(node);
  assert.equal(navigations.length, 1);
  assert.deepEqual(h.calls, []);
  assert.doesNotMatch(h.g.panel([{ ...row, source: 'other' }]), /goal-apple-report-availability/);
  assert.match(
    h.g.panel([{ ...row, state: 'APPLE_REPORT_SETUP_REQUIRED' }]),
    /apple-analytics-open/,
  );
});
