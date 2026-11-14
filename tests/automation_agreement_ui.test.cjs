const { test } = require('node:test'),
  assert = require('node:assert/strict'),
  fs = require('./helpers/module-source.cjs'),
  vm = require('node:vm'),
  path = require('node:path');
function fixture() {
  const c = {
    esc: (v) =>
      String(v ?? '')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;'),
    button: () => '',
    state: { app: 'one', workspace: { app: { version: 1 }, identity: { principal: 'owner' } } },
  };
  vm.createContext(c);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '../mission_control/static/guided-workflow.mjs'), 'utf8'),
    c,
  );
  return vm.runInContext('WMMAgreement', c);
}
test('selection includes exact existing resource IDs, never new authority fields', () => {
  const a = fixture();
  const s = a.selection(
    { schedule_batch_id: 'batch', owner: 'forged', spend: 999 },
    { version: 3 },
  );
  assert.deepEqual(Object.keys(s).sort(), [
    'campaign_scope_id',
    'manifest_version',
    'schedule_batch_id',
    'workflow_policy_id',
  ]);
  assert.equal(s.schedule_batch_id, 'batch');
  assert.equal(s.manifest_version, 3);
  assert.throws(() => a.selection({}, { version: 3 }));
});
test('combined review escapes source content and explicitly issues no authority', () => {
  const a = fixture(),
    data = {
      status: 'warning',
      summary_hash: 'hash',
      summary: {
        app: { id: '<script>', version: 1 },
        owner: { principal: 'owner' },
        local_work: null,
        campaign: null,
        schedule: null,
        stop_rules: ['<img>'],
        revocation: 'OFF keeps receipts',
      },
    };
  const html = a.markup(data);
  assert.ok(html.includes('No execution authority is issued'));
  assert.equal(html.includes('<script>'), false);
  assert.equal(html.includes('<img>'), false);
  assert.match(html, /No local-work scope selected/);
  assert.match(html, /No campaign scope selected/);
});
test('agreement report projects states and excludes private post and credential payloads', () => {
  const a = fixture(),
    data = {
      summary_hash: 'hash',
      observed_at: 'now',
      summary: {
        app: { id: 'one', version: 1 },
        blocked: false,
        local_work: null,
        campaign: {
          id: 'scope',
          effective_status: 'ACTIVE',
          commitment_held_minor: 10,
          approval: { max_total_minor: 100, currency: 'CAD' },
          private_key: 'SECRET',
          draft_posts: [
            { message: 'DRAFT_COPY', link: 'https://example.test/?utm_campaign=PRIVATE_TAG' },
          ],
        },
        schedule: {
          id: 'batch',
          effective_status: 'ACTIVE',
          items: [{ request: { message: 'PRIVATE_COPY' } }],
        },
      },
    };
  const model = a.reportModel(data, { notes: [], cohorts: [] });
  assert.doesNotMatch(JSON.stringify(model), /PRIVATE_COPY|DRAFT_COPY|PRIVATE_TAG|SECRET/);
  assert.equal(model.metrics[0].value, 2);
  assert.match(model.notes.join(' '), /No approval/);
});

test('owner report includes exact local-work identity, scope, expiry, call quota and zero spend only', () => {
  const a = fixture(),
    privatePayload = 'PRIVATE_LOCAL_PAYLOAD',
    data = {
      summary_hash: 'hash',
      observed_at: 'now',
      summary: {
        app: { id: 'one', version: 1 },
        blocked: false,
        local_work: {
          id: 'policy-1',
          effective_status: 'ACTIVE',
          summary: {
            inventory: { selection: { agent_id: 'agent-7' } },
            operations: ['evidence.read', 'brief.create'],
            stops_at: '2026-11-06T18:00:00Z',
            private_payload: privatePayload,
          },
          usage: { used: 3, max_calls: 20 },
          spend_limit_minor: 0,
        },
        campaign: null,
        schedule: null,
      },
    };
  const report = a.reportModel(data, { notes: [], cohorts: [] }),
    notes = report.notes.join(' ');
  for (const expected of [
    'Local policy policy-1 ACTIVE',
    'local-work agent agent-7',
    'Local-work permitted operations evidence.read, brief.create',
    'Local-work permission expires 2026-11-06T18:00:00Z',
    'Local-work calls 3/20',
    'Local-work spend limit 0 minor',
  ])
    assert.ok(notes.includes(expected), expected);
  assert.equal(JSON.stringify(report).includes(privatePayload), false);
  const sparse = a
    .reportModel(
      {
        ...data,
        summary: {
          ...data.summary,
          local_work: {
            id: 'sparse',
            effective_status: 'BLOCKED',
            summary: {},
            usage: {},
            spend_limit_minor: 0,
          },
        },
      },
      { notes: [], cohorts: [] },
    )
    .notes.join(' ');
  assert.match(sparse, /Local-work permitted operations Unavailable/);
  assert.match(sparse, /Local-work permission expires Unavailable/);
  assert.match(sparse, /Local-work calls Unknown\/Unknown/);
});

test('paid review displays exact budgets, uncertainty, receipt identities and repair state', () => {
  const a = fixture(),
    data = {
      status: 'warning',
      summary_hash: 'hash',
      summary: {
        app: { id: 'one', version: 1 },
        owner: { principal: 'owner' },
        local_work: {
          effective_status: 'BLOCKED',
          repair: 'Reconnect before reapproval',
          summary: {},
          usage: {},
        },
        campaign: {
          effective_status: 'ACTIVE',
          approval: {
            page_id: '123',
            ad_account_id: '456',
            expires_at: 'later',
            max_posts: 1,
            max_campaigns: 1,
            max_calls: 50,
            max_total_minor: 100,
            currency: 'CAD',
          },
          commitment_held_minor: 80,
          account: {},
          blockers: [],
        },
        schedule: {
          id: 'batch',
          effective_status: 'BLOCKED',
          blockers: ['SCHEDULE_ITEM_NEEDS_REVIEW'],
          items: [
            {
              operation: 'campaign.ad-launch',
              due_at: 'due',
              effective_status: 'NEEDS_RECONCILIATION',
              request: {
                post_id: '123_777',
                lifetime_budget_minor: 80,
                end_time: 'end',
                targeting: { countries: ['CA', 'US'] },
              },
              job_status: 'SUCCEEDED',
              intent: {
                status: 'PENDING_ACTIVATE_campaign',
                commitment: 80,
                currency: 'CAD',
                ids: { ad: '104', campaign: '101' },
              },
            },
          ],
        },
        stop_rules: [],
        revocation: 'OFF',
      },
    };
  data.summary.campaign.permission_expires_at = 'extended-parent-date';
  data.summary.schedule.permission_expires_at = 'earlier-child-date';
  const html = a.markup(data);
  for (const text of [
    '80 minor CAD',
    'ends end',
    'CA, US',
    'NEEDS_RECONCILIATION',
    'ad: 104',
    'campaign: 101',
    'SCHEDULE_ITEM_NEEDS_REVIEW',
    'Reconnect before reapproval',
    'Permission expires extended-parent-date',
    'original approval later',
    'captured deadline earlier-child-date',
  ])
    assert.ok(html.includes(text), text);
  const notes = a.reportModel(data, { notes: [] }).notes;
  assert.ok(
    notes.some((note) =>
      note.includes('Page for posts Facebook Page 123 · paid promotion Meta ad account 456'),
    ),
  );
  assert.ok(notes.some((note) => note.includes('Scope destination Meta ad account 456')));
  assert.ok(
    notes.some((note) =>
      note.includes(
        'Permission expires extended-parent-date · original approval later · posts 1 · campaigns 1 · calls 50',
      ),
    ),
  );
  assert.match(html, /Scope destination Meta ad account 456/);
  assert.equal(data.summary.campaign.approval.expires_at, 'later');

  data.summary.campaign.approval.ad_account_id = null;
  data.summary.schedule.items = [{ item_id: 'older-item', request: { message: 'PRIVATE_COPY' } }];
  const organicNotes = a.reportModel(data, { notes: [] }).notes.join(' ');
  assert.match(organicNotes, /paid promotion None selected/);
  assert.match(organicNotes, /older-item campaign.publish .*Scope destination Facebook Page 123/);
  assert.doesNotMatch(organicNotes, /PRIVATE_COPY/);

  data.summary.schedule.items[0].operation = 'unsupported.publish';
  data.summary.campaign.approval.page_id = '<credential>';
  const badNotes = a.reportModel(data, { notes: [] }).notes.join(' ');
  assert.match(badNotes, /unsupported.publish .*Scope destination Unavailable/);
  assert.doesNotMatch(badNotes, /<credential>/);
});

test('agreement and owner report show per-campaign cap and exact approved fingerprints without private payloads', () => {
  const a = fixture(),
    content = 'a'.repeat(64),
    rights = 'b'.repeat(64),
    targeting = 'c'.repeat(64);
  const data = {
    status: 'success',
    summary_hash: 'hash',
    observed_at: 'now',
    summary: {
      app: { id: 'one', version: 1 },
      owner: { principal: 'owner' },
      local_work: null,
      campaign: {
        id: 'scope',
        effective_status: 'ACTIVE',
        commitment_held_minor: 0,
        approval: {
          page_id: '123',
          max_campaign_minor: 50,
          max_total_minor: 100,
          currency: 'CAD',
          approved_content_hashes: [content],
          approved_rights_hashes: [rights],
          approved_targeting_hashes: [targeting],
        },
        account: {},
        blockers: [],
        billing_notice: 'Billing notice',
        rights_notice: 'PRIVATE_RIGHTS_PROSE',
      },
      schedule: null,
      stop_rules: [],
      revocation: 'OFF',
    },
  };
  const html = a.markup(data),
    report = a.reportModel(data, { notes: [] }),
    notes = report.notes.join(' ');
  assert.match(html, /Per-campaign media cap 50 minor CAD/);
  assert.match(html, /maximum total media commitment 100 minor CAD/);
  assert.match(html, /Exact approved content, rights and targeting hashes/);
  for (const hash of [content, rights, targeting]) {
    assert.ok(html.includes(hash));
    assert.ok(notes.includes(hash));
  }
  assert.match(notes, /Per-campaign media cap 50 minor CAD/);
  assert.match(notes, /Maximum total media commitment 100 minor CAD/);
  assert.equal(JSON.stringify(report).includes('PRIVATE_RIGHTS_PROSE'), false);
  assert.equal(JSON.stringify(report).includes('PRIVATE_COPY'), false);
});
function interactive() {
  const nodes = new Map(),
    requests = [],
    c = {
      esc: String,
      button: () => '',
      state: { app: 'one', workspace: { app: { version: 1 }, identity: { principal: 'owner' } } },
      FormData: class {
        constructor(form) {
          return Object.entries(form.values || {});
        }
      },
    };
  nodes.set('#modal', { open: true });
  c.$ = (selector) => nodes.get(selector);
  c.modal = (title, html) => {
    for (const [key, node] of nodes) if (key !== '#modal') node.isConnected = false;
    for (const match of html.matchAll(/id="([^"]+)"/g)) {
      const submit = { disabled: false },
        error = { textContent: '' };
      nodes.set('#' + match[1], {
        isConnected: true,
        values: { schedule_batch_id: 'batch' },
        querySelector: (selector) => (selector === '[type=submit]' ? submit : error),
      });
    }
    requests.push({ title, html });
  };
  c.api = async () => ({ policies: [], scopes: [], batches: [] });
  vm.createContext(c);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '../mission_control/static/guided-workflow.mjs'), 'utf8'),
    c,
  );
  return { a: vm.runInContext('WMMAgreement', c), c, nodes, requests };
}
test('late scope lists are discarded after app, manifest, owner or modal changes', async () => {
  for (const change of [
    (h) => (h.c.state.app = 'two'),
    (h) => h.c.state.workspace.app.version++,
    (h) => (h.c.state.workspace.identity.principal = 'other'),
    (h) => (h.nodes.get('#modal').open = false),
    (h) => h.c.modal('Another task', '<div id="other"></div>'),
  ]) {
    const h = interactive(),
      pending = [];
    h.c.api = () => new Promise((resolve) => pending.push(resolve));
    const opening = h.a.open();
    change(h);
    pending.forEach((resolve) => resolve({ policies: [], scopes: [], batches: [] }));
    await opening;
    assert.equal(h.nodes.has('#agreement-form'), false);
  }
});
test('preview is single flight and ignores late readback after context changes', async () => {
  for (const change of [
    (h) => (h.c.state.app = 'two'),
    (h) => h.c.state.workspace.app.version++,
    (h) => (h.c.state.workspace.identity.principal = 'other'),
    (h) => (h.nodes.get('#modal').open = false),
    (h) => h.c.modal('Another task', '<div id="other"></div>'),
  ]) {
    const h = interactive();
    await h.a.open();
    let resolve,
      calls = 0;
    h.c.api = () => {
      calls++;
      return new Promise((r) => (resolve = r));
    };
    const form = h.nodes.get('#agreement-form'),
      first = h.a.submit(form);
    await h.a.submit(form);
    assert.equal(calls, 1);
    change(h);
    resolve({ summary: {} });
    await first;
    assert.equal(h.nodes.has('#agreement-summary'), false);
    assert.equal(form.querySelector('[type=submit]').disabled, false);
  }
});

test('summary prioritizes uncertainty and preserves a concrete existing repair route', () => {
  const a = fixture();
  const uncertain = a.guidance({
    dispatch_uncertain: true,
    campaign: { effective_status: 'ACTIVE' },
  });
  assert.equal(uncertain.tool, 'campaign');
  assert.match(uncertain.label, /reconciliation/);
  assert.match(uncertain.next, /before any retry/);
  assert.equal(
    a.guidance({ local_work: { effective_status: 'OFF', repair: 'Renew exact scope' } }).next,
    'Renew exact scope',
  );
  assert.equal(a.guidance({ schedule: { effective_status: 'OFF' } }).tool, 'schedule');
  assert.equal(a.guidance({ campaign: { effective_status: 'ACTIVE' } }).tool, null);
});

test('campaign report selects no executor even alongside a local policy agent', () => {
  for (const local_work of [
    null,
    {
      id: 'local',
      effective_status: 'ACTIVE',
      summary: { inventory: { selection: { agent_id: 'local-only-agent' } } },
    },
  ]) {
    const a = fixture();
    const data = {
      summary_hash: 'hash',
      observed_at: 'now',
      summary: {
        app: { id: 'one', version: 1 },
        owner: { principal: 'owner' },
        local_work,
        campaign: {
          id: 'scope',
          effective_status: 'ACTIVE',
          commitment_held_minor: 0,
          approval: { max_total_minor: 1, currency: 'CAD' },
        },
        schedule: null,
      },
    };
    const report = a.reportModel(data, { notes: [] });
    assert.match(report.notes.join(' '), /No agent selected by campaign scope/);
    assert.match(report.notes.join(' '), /separate owner, worker or scoped grant authority/);
    if (local_work) assert.match(report.notes.join(' '), /local-work agent local-only-agent/);
    assert.equal(
      report.notes.some((note) => note.includes('Campaign agent local-only-agent')),
      false,
    );
  }
});

test('scheduled campaign names its worker, owner and saved scopes independently of the local agent', () => {
  const a = fixture(),
    data = {
      status: 'success',
      summary_hash: 'hash',
      observed_at: 'now',
      summary: {
        app: { id: 'one', version: 1 },
        owner: { principal: '<owner>' },
        local_work: {
          id: 'local',
          effective_status: 'ACTIVE',
          summary: { inventory: { selection: { agent_id: 'local-only-agent' } } },
          usage: {},
        },
        campaign: {
          id: '<campaign>',
          effective_status: 'ACTIVE',
          commitment_held_minor: 0,
          approval: { page_id: '123', max_total_minor: 0, currency: 'CAD' },
          account: {},
          blockers: [],
        },
        schedule: { id: '<batch>', effective_status: 'ACTIVE', items: [], blockers: [] },
        stop_rules: [],
        revocation: 'OFF',
      },
    };
  for (const state of ['ACTIVE', 'OFF', 'BLOCKED']) {
    data.summary.schedule.effective_status = state;
    const html = a.markup(data),
      notes = a.reportModel(data, { notes: [] }).notes.join(' ');
    assert.match(html, /Scheduled executor when the batch is active/);
    assert.match(html, /WMM background worker/);
    assert.match(html, /Owner &lt;owner&gt;/);
    assert.match(html, /Batch &lt;batch&gt;/);
    assert.match(html, /Campaign scope &lt;campaign&gt;/);
    assert.equal(html.includes('<owner>'), false);
    assert.match(notes, /WMM background worker/);
    assert.match(notes, /Owner <owner>/);
    assert.match(notes, /Batch <batch>/);
    assert.match(notes, /Campaign scope <campaign>/);
    assert.match(notes, /local-work agent local-only-agent/);
    assert.equal(notes.includes('Campaign agent local-only-agent'), false);
  }
});

test('an unreadable batch cannot be selected while healthy schedules remain available', async () => {
  const h = interactive();
  h.c.api = async () => ({
    policies: [],
    scopes: [],
    batches: [
      { id: 'damaged', status: 'NEEDS_REPAIR', evidence_unavailable: true },
      { id: 'healthy', status: 'ACTIVE' },
    ],
  });
  await h.a.open();
  const { html } = h.requests.at(-1);
  assert.match(html, /<option value="damaged" disabled>damaged · Review saved campaign receipts/);
  assert.match(html, /<option value="healthy">healthy · ACTIVE/);
});

test('agreement distinguishes exact recovery routes for expired, uncertain and standalone campaign scope', () => {
  const a = fixture(),
    campaign = { id: 'scope', effective_status: 'BLOCKED' };
  const schedule = {
    id: 'batch',
    effective_status: 'BLOCKED',
    blockers: ['SCHEDULE_PERMISSION_EXPIRED'],
    items: [],
  };
  assert.equal(a.guidance({ campaign, schedule }).tool, 'schedule');
  assert.equal(a.guidance({ campaign, schedule, dispatch_uncertain: true }).tool, 'campaign');
  schedule.items.push({ effective_status: 'NEEDS_RECONCILIATION' });
  assert.equal(a.guidance({ campaign, schedule, dispatch_uncertain: true }).tool, 'schedule');
  assert.equal(a.guidance({ campaign }).tool, 'campaign');
});
