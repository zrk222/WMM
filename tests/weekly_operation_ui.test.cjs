const { test } = require('node:test'),
  assert = require('node:assert/strict'),
  fs = require('./helpers/module-source.cjs'),
  vm = require('node:vm'),
  path = require('node:path');
const reportModule = { exports: {} };
new Function(
  'module',
  fs.readFileSync(path.join(__dirname, '../mission_control/static/page-reporting.js'), 'utf8'),
)(reportModule);
const src = fs.readFileSync(
  path.join(__dirname, '../mission_control/static/app-weekly.mjs'),
  'utf8',
);
const start = src.indexOf('function visibleWeeklyExceptions('),
  end = src.indexOf('function weeklyView()', start),
  c = { WMMPageReports: reportModule.exports };
vm.createContext(c);
vm.runInContext(src.slice(start, end), c);

test('schedule recovery opens only the reviewed batch and ignores refreshed identity drift', async () => {
  const begin = src.indexOf('async function weeklyAction(');
  const finish = src.indexOf('function ', begin + 10);
  const card = {
    app_id: 'one',
    category: 'scheduled_campaign',
    resolution_route: 'campaign',
    owner_only: true,
    owner_principal: 'owner',
    action: { scope_id: 'scope', batch_id: 'batch' },
  };
  for (const scenario of [
    'match',
    'wrong batch',
    'wrong scope',
    'changed owner',
    'changed view',
    'foreign card',
  ]) {
    const calls = [];
    const state = {
      app: 'one',
      view: 'weekly',
      boot: { apps: [{ id: 'one' }] },
      workspace: { identity: { principal: 'owner' } },
      weeklyReview: {
        owner_operations_principal: 'owner',
        exceptions: [scenario === 'foreign card' ? { ...card, app_id: 'two' } : card],
      },
    };
    const context = {
      state,
      $: () => ({}),
      currentWorkspace: () => true,
      visibleWeeklyExceptions: c.visibleWeeklyExceptions,
      refresh: async () => {
        calls.push('refresh');
        if (scenario === 'changed owner') state.workspace.identity.principal = 'other';
        if (scenario === 'changed view') state.view = 'results';
      },
      campaignScheduleStatus: (id) => calls.push('batch:' + id),
      campaignStatus: (id) => calls.push('scope:' + id),
    };
    vm.createContext(context);
    vm.runInContext(src.slice(begin, finish), context);
    const action = context.weeklyAction({
      dataset: {
        action: 'weekly-recover',
        app: 'one',
        tool: 'campaign',
        category: 'scheduled_campaign',
        resource: scenario === 'wrong batch' ? 'forged' : 'batch',
        scope: scenario === 'wrong scope' ? 'another' : 'scope',
      },
    });
    if (['wrong batch', 'wrong scope', 'foreign card'].includes(scenario)) {
      await assert.rejects(action, /Refresh this review before opening the schedule/);
      assert.deepEqual(calls, []);
      continue;
    }
    await action;
    assert.equal(calls[0], 'refresh');
    assert.equal(calls.includes('batch:batch'), scenario === 'match');
    assert.equal(calls.length, scenario === 'changed owner' || scenario === 'changed view' ? 1 : 2);
  }
});
test('cached owner operations require matching response and current card principal', () => {
  const value = {
    owner_operations_principal: 'owner',
    exceptions: [
      { id: 'public' },
      { id: 'private', owner_only: true, owner_principal: 'owner' },
      { id: 'foreign', owner_only: true, owner_principal: 'other' },
    ],
  };
  assert.deepEqual(
    Array.from(c.visibleWeeklyExceptions(value, 'owner'), (x) => x.id),
    ['public', 'private'],
  );
  for (const principal of [null, undefined, 'other'])
    assert.deepEqual(
      Array.from(c.visibleWeeklyExceptions(value, principal), (x) => x.id),
      ['public'],
    );
  assert.deepEqual(
    Array.from(
      c.visibleWeeklyExceptions({ ...value, owner_operations_principal: null }, 'owner'),
      (x) => x.id,
    ),
    ['public'],
  );
});

test('operational recovery uses fixed exact-resource controls after current app refresh', async () => {
  const begin = src.indexOf('async function weeklyAction('),
    finish = src.indexOf('function ', begin + 10);
  const actionSource = src.slice(begin, finish);
  for (const tool of ['monitor', 'campaign', 'owner_reports']) {
    const calls = [],
      state = {
        app: 'one',
        view: 'weekly',
        boot: { apps: [{ id: 'one' }] },
        workspace: { app: { version: 1 }, identity: { principal: 'owner' } },
      },
      c = {
        state,
        $: () => ({ value: 'one' }),
        refresh: async () => calls.push('refresh'),
        currentWorkspace: () => true,
        WMMCampaignMonitor: {
          open: async () => calls.push('monitor-open'),
          inspect: async (id) => calls.push(id),
        },
        WMMOwnerReports: {
          open: async () => calls.push('reports-open'),
          inspect: async (kind, id) => calls.push(kind + ':' + id),
        },
        campaignStatus: async (id) => calls.push('scope:' + id),
      };
    vm.createContext(c);
    vm.runInContext(actionSource, c);
    await c.weeklyAction({
      dataset: {
        action: 'weekly-recover',
        app: 'one',
        tool,
        resource: 'exact-id',
        scope: 'scope-id',
      },
    });
    assert.equal(calls[0], 'refresh');
    assert.equal(
      calls.at(-1),
      tool === 'monitor' ? 'exact-id' : tool === 'campaign' ? 'scope:scope-id' : 'plan:exact-id',
    );
  }
});

test('review recovery inspects only the visible exact resource after refreshed context checks', async () => {
  const begin = src.indexOf('async function weeklyAction('),
    finish = src.indexOf('function ', begin + 10);
  for (const drift of ['none', 'principal', 'app', 'view']) {
    const calls = [],
      card = {
        app_id: 'one',
        resolution_route: 'agent_review',
        action: { resource_id: 'review-one' },
        private_principal: 'checker',
      };
    const state = {
      app: 'one',
      view: 'weekly',
      boot: { apps: [{ id: 'one' }] },
      workspace: { app: { version: 1 }, identity: { principal: 'checker' } },
      weeklyReview: { owner_operations_principal: 'checker', exceptions: [card] },
    };
    const context = {
      state,
      $: () => ({ value: 'one' }),
      visibleWeeklyExceptions: reportModule.exports.visibleWeeklyExceptions,
      refresh: async () => {
        calls.push('refresh');
        if (drift === 'principal') state.workspace.identity.principal = 'other';
        if (drift === 'app') state.app = 'two';
        if (drift === 'view') state.view = 'overview';
      },
      currentWorkspace: () => true,
      growthReviewServices: () => ({ inspection: true }),
      WMMAgentControl: {
        action: async (node, services) =>
          calls.push({ action: node.dataset.action, id: node.dataset.id, services }),
      },
    };
    vm.createContext(context);
    vm.runInContext(src.slice(begin, finish), context);
    await context.weeklyAction({
      dataset: {
        action: 'weekly-recover',
        app: 'one',
        tool: 'agent_review',
        resource: 'review-one',
      },
    });
    assert.equal(calls[0], 'refresh');
    assert.equal(calls.length, drift === 'none' ? 2 : 1);
    if (drift === 'none') {
      assert.equal(calls[1].action, 'control-inspect');
      assert.equal(calls[1].id, 'review-one');
    }
  }
});

test('review recovery rejects a forged resource or a cached foreign response before refresh', async () => {
  const begin = src.indexOf('async function weeklyAction('),
    finish = src.indexOf('function ', begin + 10);
  for (const foreign of [false, true]) {
    const state = {
      app: 'one',
      view: 'weekly',
      boot: { apps: [{ id: 'one' }] },
      workspace: { identity: { principal: 'checker' } },
      weeklyReview: {
        owner_operations_principal: foreign ? 'other' : 'checker',
        exceptions: [
          {
            app_id: 'one',
            resolution_route: 'agent_review',
            action: { resource_id: 'allowed' },
            private_principal: 'checker',
          },
        ],
      },
    };
    const context = {
      state,
      visibleWeeklyExceptions: reportModule.exports.visibleWeeklyExceptions,
      refresh: async () => assert.fail('must not refresh forged request'),
    };
    vm.createContext(context);
    vm.runInContext(src.slice(begin, finish), context);
    await assert.rejects(
      context.weeklyAction({
        dataset: {
          action: 'weekly-recover',
          app: 'one',
          tool: 'agent_review',
          resource: foreign ? 'allowed' : 'forged',
        },
      }),
      /Refresh this signed-in review/,
    );
  }
});

test('damaged review metadata opens the existing queue rather than a synthetic missing request', async () => {
  const begin = src.indexOf('async function weeklyAction('),
    finish = src.indexOf('function ', begin + 10),
    calls = [];
  const state = {
    app: 'one',
    view: 'weekly',
    boot: { apps: [{ id: 'one' }] },
    workspace: { app: { version: 1 }, identity: { principal: 'checker' } },
    weeklyReview: {
      owner_operations_principal: 'checker',
      exceptions: [
        {
          app_id: 'one',
          state: 'SOURCE_UNAVAILABLE',
          resolution_route: 'agent_review',
          action: { resource_id: 'review-source' },
          private_principal: 'checker',
        },
      ],
    },
  };
  const context = {
    state,
    $: () => ({ value: 'one' }),
    visibleWeeklyExceptions: reportModule.exports.visibleWeeklyExceptions,
    refresh: async () => calls.push('refresh'),
    currentWorkspace: () => true,
    growthReviewServices: () => ({}),
    WMMAgentControl: { action: async (node) => calls.push(node.dataset.action) },
  };
  vm.createContext(context);
  vm.runInContext(src.slice(begin, finish), context);
  await context.weeklyAction({
    dataset: {
      action: 'weekly-recover',
      app: 'one',
      tool: 'agent_review',
      resource: 'review-source',
    },
  });
  assert.deepEqual(calls, ['refresh', 'control-queue']);
});
