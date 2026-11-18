const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const holder = { exports: {} };
new Function('module', fs.readFileSync('mission_control/static/apple-analytics.js', 'utf8'))(
  holder,
);
const apple = holder.exports;

function fixture() {
  const state = {
    app: 'one',
    view: 'connections',
    boot: { csrf: 'csrf-1' },
    workspace: {
      app: { id: 'one', version: 2, data: { store_app_id: '123' } },
      identity: { status: 'AUTHENTICATED', principal: 'owner', expires_at_epoch: 9999999999 },
      access: {
        configured: true,
        members: [{ principal: 'owner', status: 'ACTIVE', role: 'OWNER', version: 1 }],
      },
      records: [
        {
          id: 'connection-1',
          version: 3,
          hash: 'hash-1',
          kind: 'connection',
          data: { provider: 'app_store', store_app_id: '123' },
        },
      ],
    },
  };
  const data = {
    app_id: 'one',
    manifest_version: 2,
    store_app_id: '123',
    connection: { id: 'connection-1', version: 3, status: 'CONFIGURED_UNVERIFIED' },
    inventory: {
      job_id: 'job-1',
      status: 'WAITING_FOR_REPORTS',
      observed_at: '2026-01-01T00:00:00Z',
    },
    reports: [
      { id: 'report-1', name: 'App Downloads Standard', instance_count: 0, coverage: 'COMPLETE' },
    ],
    schedule: null,
  };
  let html = '',
    node = null;
  const dialog = { open: false };
  const d = {
    state,
    document: { querySelector: (s) => (s === '#modal' ? dialog : node) },
    modal: (title, body) => {
      if (node) node.isConnected = false;
      html = body;
      dialog.open = true;
      const fields = {
        '#apple-analytics-status': { textContent: '' },
        '#apple-analytics-error': { textContent: '' },
        '#apple-performance-status': { textContent: '' },
        '#apple-performance-error': { textContent: '' },
        '#apple-performance-receipt': { innerHTML: '' },
        '#apple-performance-results': { innerHTML: '', querySelectorAll: () => [] },
      };
      node = {
        isConnected: true,
        fields,
        setAttribute() {},
        querySelector: (s) => fields[s],
        querySelectorAll: () => [],
      };
    },
    api: async () => data,
    uuid: () => '00000000-0000-4000-8000-000000000001',
    FormData: class {
      constructor(form) {
        this.values = form.values;
      }
      get(key) {
        return this.values[key];
      }
    },
    close: () => {
      dialog.open = false;
    },
    connectionSetup() {},
    openAccess() {},
    browser: {},
    pageReports: {
      model: () => ({ filters: {}, notes: [], metrics: [], cohorts: [] }),
      appReportModel: () => ({ filters: {}, notes: [], metrics: [], cohorts: [] }),
      openReport() {},
    },
  };
  return {
    d,
    data,
    state,
    dialog,
    get html() {
      return html;
    },
    get node() {
      return node;
    },
  };
}
const defer = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
};
function form(values = { report_id: 'report-1', interval_hours: '24' }) {
  return { id: 'apple-analytics-form', isConnected: true, values };
}
function click(action) {
  return { dataset: { action: 'apple-analytics-' + action } };
}

function searchFixture(f) {
  const dates = { start: '2026-11-13', end: '2026-11-17' };
  const draft = {
    task: 'Check the current source.',
    metric: 'Observed rows',
    guardrail: 'Preserve source scopes.',
    follow_up: 'After the next saved reading.',
    agent: 'Measurement reviewer',
  };
  return {
    form: { id: 'apple-performance-form', isConnected: true, values: dates },
    result: {
      app_id: f.state.app,
      store_app_id: '123',
      ...dates,
      rows: [
        {
          date: dates.start,
          discovery: {
            counts: { impressions: '0', page_views: null },
            status: 'APPLE_REPORTED',
            processing_date: '2026-11-16',
            source_sha256: 'apple-file-hash',
          },
          downloads: {
            counts: { first_time_downloads: null, redownloads: null },
            status: 'NO_FILE',
            processing_date: null,
            source_sha256: null,
          },
        },
      ],
      search_review: {
        insight: 'Read the <owned page> evidence.',
        next_action: 'Review the link path',
        success_metric: 'Eligible sessions with a store click',
        guardrail: 'Preserve the web CTA.',
        follow_up: 'After the selected window is complete.',
        web_source: 'Saved OpenSEO reading',
        web_facts: ['US · 28 days ending November 14, 2026'],
        web_evidence_sha256: 'seo-report-hash',
        evidence_status: 'Whole windows differ',
        review_hash: 'exact-review-hash',
        saved_actions: [],
        team_agents: [{ grant_id: 'grant-1', agent_id: 'actual-agent' }],
        assignments: {},
        actions: [
          { ...draft, id: 'web-baseline', title: 'Review the web baseline', depends_on: [] },
          {
            ...draft,
            id: 'store-link-check',
            title: 'Inspect the store link',
            depends_on: ['web-baseline'],
          },
        ],
      },
    },
  };
}

test('combined review keeps measured zero, independent source windows and dependent drafts in the PDF and JSON', async () => {
  const f = fixture();
  const { form, result } = searchFixture(f);
  const calls = [];
  let pdf, json;
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    return path.endsWith('/view') ? f.data : result;
  };
  f.d.pageReports.openReport = (report) => {
    pdf = report;
    return {
      close() {
        pdf = null;
      },
    };
  };
  f.d.download = (name, data) => {
    json = { name, data };
  };
  await apple.action(click('open'), f.d);
  assert.match(apple.reviewPanel(), /Open Search to App Store/);
  assert.match(f.html, /Review search and App Store results/);
  await apple.submit(form, f.d, 'search');
  assert.deepEqual(calls.at(-1), {
    path: '/api/apps/one/apple-analytics/search-review',
    body: { manifest_version: 2, start: '2026-11-13', end: '2026-11-17' },
  });
  const output = f.node.fields['#apple-performance-results'];
  assert.match(output.innerHTML, /Read the &lt;owned page&gt; evidence/);
  assert.match(output.innerHTML, /<td>0<\/td><td>Unavailable<\/td>/);
  assert.match(output.innerHTML, /After Review the web baseline/);
  await apple.action(click('search-report'), f.d);
  assert.equal(pdf.title, 'Search to App Store');
  assert.equal(pdf.next_step, 'Review the link path');
  assert.equal(pdf.sections.at(-1).items.length, 2);
  assert.equal(pdf.sections.at(-1).items[1].facts.at(-1)[1], 'After Review the web baseline');
  await apple.action(click('search-download'), f.d);
  assert.equal(json.name, 'search-to-app-store-plan.json');
  assert.equal(json.data.search_review.web_evidence_sha256, 'seo-report-hash');
  f.state.workspace.insights = { sources: [{ provider: 'openseo', id: 'changed' }] };
  apple.invalidate(f.state);
  assert.equal(pdf, null);
  assert.equal(output.innerHTML, '');
});

test('prior review receipts survive in read-only history, print and JSON', async () => {
  const f = fixture();
  const { form, result } = searchFixture(f);
  const prior = {
    review_hash: 'earlier-review',
    saved_actions: [
      {
        id: 'saved-draft',
        action_id: 'web-baseline',
        action: { title: 'Prior <web> analysis' },
        created: '2026-11-17T23:24:00Z',
      },
    ],
    assignments: {
      'web-baseline': {
        agent_id: 'analyst',
        status: 'COMPLETED',
        receipt_sha256: 'prior-execution-hash',
        deliverable: { summary: 'Recorded the baseline.', details: { clicks: 4 } },
      },
    },
  };
  result.search_review.earlier_plans = [prior];
  let pdf, json;
  f.d.api = async (path) => (path.endsWith('/view') ? f.data : result);
  f.d.pageReports.openReport = (report) => {
    pdf = report;
  };
  f.d.download = (_name, data) => {
    json = data;
  };
  await apple.open(f.d);
  await apple.submit(form, f.d, 'search');
  const history = f.node.fields['#apple-performance-results'].innerHTML.match(
    /<details data-search-history>(.*?)<\/details>/s,
  )[1];
  assert.match(history, /Prior &lt;web&gt; analysis/);
  assert.match(history, /prior-execution-hash/);
  assert.match(history, /Completed/);
  assert.doesNotMatch(history, /<button|<select|data-action/);
  await apple.action(click('search-report'), f.d);
  const earlier = pdf.sections.find((s) => s.title === 'Earlier plan receipts for these dates');
  assert.deepEqual(
    earlier.items[0].facts.find(([key]) => key === 'Execution receipt SHA-256'),
    ['Execution receipt SHA-256', 'prior-execution-hash'],
  );
  await apple.action(click('search-download'), f.d);
  assert.deepEqual(json.search_review.earlier_plans, [prior]);
});

function appleReceipt(result, status, fields = {}) {
  return {
    app_id: result.app_id,
    store_app_id: result.store_app_id,
    start: result.start,
    end: result.end,
    refresh_id: 'apple-fetch-123',
    status,
    inventory_job_id: 'inventory-run',
    inventory_status: 'SUCCEEDED',
    provider_status: 'METRIC_DOWNLOAD_REQUIRED',
    coverage: 'COMPLETE',
    files: [],
    ...fields,
  };
}

test('explicit Apple fetch follows the exact owner receipt then reads back saved counts and per-metric coverage', async () => {
  const f = fixture();
  const { form, result } = searchFixture(f);
  const calls = [];
  result.rows[0].discovery.counts.impressions = '72';
  result.outcome_coverage = {
    metrics: [
      {
        label: 'Total downloads',
        value: '0',
        scope: 'Selected Apple event days',
        repair: null,
        source_sha256: 'total-source-hash',
      },
      {
        label: 'Paid subscriptions',
        value: null,
        scope: 'Verified paid cohort',
        repair: 'Measure a named paid cohort.',
        source_sha256: null,
      },
    ],
    cohorts: [],
  };
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    if (path.endsWith('/view')) return f.data;
    if (path.endsWith('/performance-refresh')) return appleReceipt(result, 'INVENTORY');
    if (path.endsWith('/performance-refresh-status'))
      return appleReceipt(result, 'READY', {
        files: [
          {
            job_id: 'apple-source-job',
            status: 'SUCCEEDED',
            report_family: 'App Downloads Standard',
            processing_date: '2026-11-16',
          },
        ],
        secret: 'unrelated-input-must-not-export',
      });
    assert.ok(path.endsWith('/search-review'));
    return result;
  };
  let pdf, exported;
  f.d.pageReports.openReport = (model) => {
    pdf = model;
  };
  f.d.download = (_name, data) => {
    exported = data;
  };
  await apple.open(f.d);
  assert.match(f.html, /Fetch Apple analytics/);
  const job = apple.submit(form, f.d);
  await new Promise(setImmediate);
  assert.match(
    f.node.fields['#apple-performance-status'].textContent,
    /Checking Apple report availability/,
  );
  await job;
  assert.deepEqual(calls[1], {
    path: '/api/apps/one/apple-analytics/performance-refresh',
    body: {
      manifest_version: 2,
      start: result.start,
      end: result.end,
      connection_id: 'connection-1',
      connection_version: 3,
      request_id: '00000000-0000-4000-8000-000000000001',
    },
  });
  assert.match(calls[2].path, /\/performance-refresh-status$/);
  assert.match(calls[3].path, /\/search-review$/);
  assert.match(
    f.node.fields['#apple-performance-status'].textContent,
    /Apple file collection finished/,
  );
  assert.match(
    f.node.fields['#apple-performance-receipt'].innerHTML,
    /inventory-run|apple-source-job/,
  );
  const output = f.node.fields['#apple-performance-results'].innerHTML;
  assert.match(output, /<td>72<\/td>/);
  assert.match(output, /Total downloads <strong>0<\/strong>/);
  assert.match(output, /Paid subscriptions <strong>Unavailable<\/strong>/);
  assert.match(output, /Measure a named paid cohort/);
  await apple.action(click('search-report'), f.d);
  assert.ok(pdf.sections.some((section) => section.title === 'Apple fetch receipt'));
  assert.ok(pdf.sections.some((section) => section.title === 'Other Apple metrics and coverage'));
  await apple.action(click('search-download'), f.d);
  assert.equal(exported.apple_refresh.refresh_id, 'apple-fetch-123');
  assert.equal(exported.outcome_coverage.metrics[0].source_sha256, 'total-source-hash');
  assert.doesNotMatch(JSON.stringify(exported), /unrelated-input-must-not-export/);
});

test('interrupted Apple fetch reuses intent, and no matching files stay unavailable', async () => {
  const f = fixture();
  const { form, result } = searchFixture(f);
  const requestIds = [];
  let ids = 0;
  f.d.uuid = () => 'request-' + ++ids;
  result.rows[0].discovery.counts.impressions = null;
  f.d.api = async (path, body) => {
    if (path.endsWith('/view')) return f.data;
    if (path.endsWith('/performance-refresh')) {
      requestIds.push(body.request_id);
      if (requestIds.length === 1) throw Error('Response interrupted');
      return appleReceipt(result, 'NO_FILES_FOR_DATES', {
        reason: 'Apple supplied no files for the selected dates.',
      });
    }
    assert.ok(path.endsWith('/search-review'));
    return result;
  };
  await apple.open(f.d);
  await apple.submit(form, f.d, 'fetch');
  assert.match(f.node.fields['#apple-performance-error'].textContent, /interrupted/);
  await apple.submit(form, f.d, 'fetch');
  assert.deepEqual(requestIds, ['request-1', 'request-1']);
  assert.match(f.node.fields['#apple-performance-status'].textContent, /Apple supplied no files/);
  assert.match(f.node.fields['#apple-performance-results'].innerHTML, /No Apple metrics are saved/);
});

test('owner without an Apple connection can open setup directly from the performance form', async () => {
  const f = fixture();
  f.state.workspace.records = [];
  f.data.connection = null;
  const { form } = searchFixture(f);
  const opens = [];
  let posts = 0;
  f.d.api = async () => {
    posts++;
    return f.data;
  };
  f.d.connectionSetup = (provider, source) => opens.push({ provider, source });
  await apple.open(f.d);
  assert.match(f.html, /Connect App Store Connect/);
  assert.doesNotMatch(f.html, /value="fetch">/);
  await apple.submit(form, f.d, 'fetch');
  await apple.action(click('setup'), f.d);
  assert.equal(posts, 1);
  assert.deepEqual(opens, [{ provider: 'app_store', source: null }]);
});

test('campaign fetch accepts only the saved same-window owner report shown in the current review', async () => {
  const f = fixture();
  const { form, result } = searchFixture(f);
  const calls = [];
  result.outcome_coverage = {
    metrics: [
      {
        label: 'Campaign-attributed first-time downloads',
        value: null,
        scope: 'Saved owner report',
        repair: 'Fetch Detailed files for this exact approved campaign.',
        campaign_report_id: 'verified-report',
      },
    ],
    cohorts: [],
  };
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    if (path.endsWith('/view')) return f.data;
    if (path.endsWith('/campaign-refresh')) return appleReceipt(result, 'READY');
    return result;
  };
  await apple.open(f.d);
  await apple.submit(form, f.d, 'search');
  assert.match(f.node.fields['#apple-performance-results'].innerHTML, /Fetch campaign downloads/);
  const request = click('campaign-fetch');
  request.dataset.id = 'foreign-report';
  await apple.action(request, f.d);
  assert.equal(calls.length, 2);
  request.dataset.id = 'verified-report';
  await apple.action(request, f.d);
  assert.deepEqual(calls[2], {
    path: '/api/apps/one/apple-analytics/campaign-refresh',
    body: {
      manifest_version: 2,
      start: result.start,
      end: result.end,
      connection_id: 'connection-1',
      connection_version: 3,
      request_id: '00000000-0000-4000-8000-000000000001',
      campaign_report_id: 'verified-report',
    },
  });
});

test('selected search actions save and assign against the exact reviewed scope', async () => {
  const f = fixture();
  const { form, result } = searchFixture(f);
  const calls = [];
  const receipt = { id: 'receipt-1', action_id: 'web-baseline', status: 'SAVED' };
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    if (path.endsWith('/view')) return f.data;
    if (path.endsWith('/search-review-assign')) {
      result.search_review.assignments['web-baseline'] = {
        grant_id: 'grant-1',
        agent_id: 'actual-agent',
        status: 'ASSIGNED',
      };
    }
    if (path.endsWith('/search-review')) return result;
    return { app_id: 'one', review_hash: 'exact-review-hash', receipt };
  };
  await apple.open(f.d);
  await apple.submit(form, f.d, 'search');
  const selected = click('search-save');
  selected.dataset.id = 'web-baseline';
  await apple.action(selected, f.d);
  assert.deepEqual(calls.at(-1).body, {
    manifest_version: 2,
    start: result.start,
    end: result.end,
    review_hash: 'exact-review-hash',
    action_id: 'web-baseline',
  });
  assert.match(f.node.fields['#apple-performance-results'].innerHTML, /Draft saved in WMM/);
  f.node.querySelectorAll = (selector) =>
    selector === '[data-search-agent]'
      ? [{ dataset: { searchAgent: 'web-baseline' }, value: 'grant-1' }]
      : [];
  selected.dataset.action = 'apple-analytics-search-assign';
  await apple.action(selected, f.d);
  assert.equal(calls.at(-2).path, '/api/apps/one/apple-analytics/search-review-assign');
  assert.equal(calls.at(-2).body.grant_id, 'grant-1');
  assert.match(
    f.node.fields['#apple-performance-status'].textContent,
    /Step assigned to actual-agent/,
  );
  assert.match(f.node.fields['#apple-performance-results'].innerHTML, /Awaiting agent/);
});

test('shows truthful inventory, schedule and PDF evidence without private fields', async () => {
  const f = fixture();
  f.data.schedule = {
    enabled: true,
    status: 'ENABLED',
    failures: 2,
    last_job: 'refresh-1',
    last_job_status: 'FAILED',
    last_success: null,
    next_due: 1790000000,
    version: 4,
    interval_hours: 48,
    report_id: 'report-1',
  };
  f.data.secret = 'PRIVATE_SENTINEL';
  await apple.open(f.d);
  for (const text of [
    '0 report instances',
    'not downloads',
    'FAILED',
    'Failures: 2',
    'Pause refresh',
    'Refresh every (hours)',
    'Inspect latest refresh',
    'not a guarantee of current access',
  ])
    assert.ok(f.html.includes(text), text);
  assert.match(
    f.html,
    /<label for="apple-analytics-report">What should WMM check\?<\/label><select id="apple-analytics-report"/,
  );
  assert.match(
    f.html,
    /<label for="apple-analytics-interval">Refresh every \(hours\)<\/label><input id="apple-analytics-interval"/,
  );
  const value = apple.report(f.data, f.state, f.d.pageReports);
  assert.equal(value.metrics[0].value, 0);
  assert.ok(value.notes.join(' ').includes('not downloads'));
  assert.ok(!JSON.stringify(value).includes('PRIVATE_SENTINEL'));
});
test('a missing local key offers repair and keeps saved reports and pause available', async () => {
  const f = fixture(),
    calls = [];
  let repair = 0;
  f.data.connection.status = 'RECONNECT_REQUIRED';
  f.data.schedule = { enabled: true, status: 'ENABLED', version: 3, failures: 0 };
  f.data.reports.push({
    id: 'discovery-1',
    name: 'App Store Discovery and Engagement Standard',
    coverage: 'COMPLETE',
    instance_count: 0,
  });
  f.d.api = async (path) => {
    calls.push(path);
    return f.data;
  };
  f.d.connectionSetup = (provider, id) => {
    assert.equal(provider, 'app_store');
    assert.equal(id, 'connection-1');
    repair++;
  };
  await apple.open(f.d);
  assert.match(f.html, /Reconnect App Store Connect/);
  assert.match(f.html, /WAITING FOR REPORTS|0 report instances/);
  assert.match(f.html, /Pause refresh/);
  assert.match(f.html, /Inventory report \/ Save PDF/);
  assert.doesNotMatch(
    f.html,
    /Read Apple inventory|Collect store impressions|Enable refresh|Save refresh settings/,
  );
  await apple.action(click('inventory'), f.d);
  await apple.action(click('impressions'), f.d);
  await apple.submit(form(), f.d);
  assert.equal(calls.length, 1);
  await apple.action(click('setup'), f.d);
  assert.equal(repair, 1);
});

test('gives the next step for saved Apple inventory without changing credentials or reports', async () => {
  const cases = [
    ['REPORT_SETUP_REQUIRED', /App Store Connect Admin to start ongoing reporting/, true],
    ['REQUEST_INVENTORY_PARTIAL', /incomplete list of report requests/, false],
    ['WAITING_FOR_REPORTS', /No file means the download count is unknown/, false],
  ];
  for (const [status, message, hasDocs] of cases) {
    const f = fixture();
    const calls = [];
    f.data.inventory.status = status;
    f.d.api = async (path, body) => {
      calls.push({ path, body });
      return f.data;
    };
    await apple.open(f.d);
    assert.match(f.html, message);
    assert.match(apple.report(f.data, f.state, f.d.pageReports).notes.join(' '), message);
    assert.equal(f.html.includes('analytics-reports-api'), hasDocs);
    assert.equal(calls.length, 1);
    assert.match(calls[0].path, /\/view$/);
    assert.deepEqual(calls[0].body, {});
  }
  const stale = fixture();
  stale.data.inventory.status = 'REPORT_SETUP_REQUIRED';
  stale.data.connection.status = 'RECONNECT_REQUIRED';
  await apple.open(stale.d);
  assert.match(stale.html, /Next step:<\/strong> Reconnect the App Store Connect key for this app/);
  assert.doesNotMatch(stale.html, /App Store Connect Admin|analytics-reports-api/);
});

test('signed out and nonowner are routed to existing repair choices without data read', async () => {
  const f = fixture();
  let calls = 0;
  f.d.api = async () => {
    calls++;
    return f.data;
  };
  f.state.workspace.identity = { status: 'SIGNED_OUT' };
  await apple.open(f.d);
  assert.match(f.html, /Sign in/);
  assert.equal(calls, 0);
  f.state.workspace.identity = { status: 'AUTHENTICATED', principal: 'reviewer' };
  await apple.open(f.d);
  assert.match(f.html, /current app owner/);
  assert.match(f.html, /Review app access/);
  assert.equal(calls, 0);
});
test('discard async views after app, manifest, connection, session or dialog changes', async () => {
  for (const change of [
    (f) => (f.state.app = 'two'),
    (f) => f.state.workspace.app.version++,
    (f) => f.state.workspace.records[0].version++,
    (f) => (f.state.workspace.identity.principal = 'other'),
    (f) => (f.state.workspace.identity = { ...f.state.workspace.identity }),
    (f) => (f.state.boot.csrf = 'changed'),
    (f) => (f.dialog.open = false),
  ]) {
    apple.clear();
    const f = fixture(),
      pending = defer();
    f.d.api = () => pending.promise;
    const request = apple.open(f.d);
    const before = f.html;
    change(f);
    pending.resolve(f.data);
    await request;
    assert.equal(f.html, before);
  }
});
test('reject server data for stale app or connection', async () => {
  const f = fixture();
  f.data.connection.version = 99;
  await apple.open(f.d);
  assert.match(f.node.fields['#apple-analytics-error'].textContent, /connection changed/i);
  assert.doesNotMatch(f.html, /Enable refresh/);
  const g = fixture();
  g.data.store_app_id = '999';
  await apple.open(g.d);
  assert.match(g.node.fields['#apple-analytics-error'].textContent, /App setup changed/i);
});
test('save uses exact owner-visible version and prevents duplicate concurrent writes', async () => {
  const f = fixture(),
    pending = defer(),
    calls = [];
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    if (path.endsWith('/view')) return f.data;
    return pending.promise;
  };
  await apple.open(f.d);
  const saving = apple.submit(form(), f.d);
  await apple.submit(form(), f.d);
  assert.equal(calls.filter((c) => c.path.endsWith('/schedule')).length, 1);
  assert.deepEqual(calls.at(-1).body, {
    manifest_version: 2,
    enabled: true,
    interval_hours: 24,
    report_id: 'report-1',
    version: null,
  });
  pending.reject(Error('Connection lost'));
  await saving;
  assert.match(f.node.fields['#apple-analytics-error'].textContent, /No request was repeated/);
  assert.equal(calls.filter((c) => c.path.endsWith('/schedule')).length, 1);
});
test('a new source can schedule just report availability with no report ID', async () => {
  const f = fixture();
  f.data.reports = [];
  f.data.inventory = null;
  const calls = [];
  f.d.api = async (path, body) => {
    if (path.endsWith('/view')) return f.data;
    calls.push(body);
    f.data.schedule = { enabled: true, mode: 'inventory', version: 1, status: 'ENABLED' };
    return f.data.schedule;
  };
  await apple.open(f.d);
  assert.match(f.html, /What should WMM check\?[^]*Report availability/);
  assert.match(f.html, /does not collect download counts/);
  await apple.submit(form({ report_id: '@inventory', interval_hours: '24' }), f.d);
  assert.deepEqual(calls, [
    { manifest_version: 2, enabled: true, interval_hours: 24, mode: 'inventory', version: null },
  ]);
  assert.match(f.html, /On · Report availability/);
  assert.match(f.html, /Pause refresh/);
});
test('the owner can choose an explicit local start for a report watch', async () => {
  const f = fixture();
  f.data.reports = [];
  f.data.inventory = null;
  const sent = [];
  f.d.api = async (path, body) => {
    if (path.endsWith('/view')) return f.data;
    sent.push(body);
    return f.data.schedule;
  };
  await apple.open(f.d);
  assert.match(f.html, /First check time \(optional\)/);
  assert.match(f.html, /Use your device time zone/);
  const future = new Date(Date.now() + 3600000);
  future.setSeconds(0, 0);
  const local = new Date(future.getTime() - future.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
  await apple.submit(
    form({ report_id: '@inventory', interval_hours: '24', first_read_at: local }),
    f.d,
  );
  assert.deepEqual(sent, [
    {
      manifest_version: 2,
      enabled: true,
      interval_hours: 24,
      first_read_at: future.toISOString(),
      mode: 'inventory',
      version: null,
    },
  ]);
  await apple.submit(
    form({ report_id: '@inventory', interval_hours: '24', first_read_at: '2000-01-01T00:00' }),
    f.d,
  );
  assert.equal(sent.length, 1);
  assert.match(f.node.fields['#apple-analytics-error'].textContent, /next seven days/);
});
test('a bounded watch displays its stop time and never advertises a check past it', async () => {
  const f = fixture();
  const sent = [];
  const stop = new Date(Date.now() + 3600000);
  stop.setSeconds(0, 0);
  const local = new Date(stop.getTime() - stop.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
  f.d.api = async (path, body) => {
    if (path.endsWith('/view')) return f.data;
    sent.push(body);
    f.data.schedule = {
      enabled: true,
      mode: 'inventory',
      status: 'ENABLED',
      stop_at: stop.getTime() / 1000,
      next_due: stop.getTime() / 1000,
      version: 1,
    };
    return f.data.schedule;
  };
  await apple.open(f.d);
  assert.match(f.html, /Stop checking at \(optional\)/);
  await apple.submit(form({ report_id: '@inventory', interval_hours: '24', stop_at: local }), f.d);
  assert.equal(sent[0].stop_at, stop.toISOString());
  assert.match(f.html, /Next due: Not scheduled<br>Stop time:/);
  assert.match(f.html, new RegExp(`name="stop_at"[^>]*value="${local}"`));
  await apple.submit(
    form({ report_id: '@inventory', interval_hours: '24', first_read_at: local, stop_at: local }),
    f.d,
  );
  assert.equal(sent.length, 1);
  assert.match(f.node.fields['#apple-analytics-error'].textContent, /after the first check/);
  f.data.schedule = { ...f.data.schedule, status: 'EXPIRED', enabled: false };
  await apple.open(f.d);
  assert.match(f.html, /class="status expired">Check window ended<\/span> · Off/);
});
test('invalid interval or foreign report cannot write and stale session stops post-response repaint', async () => {
  const f = fixture(),
    pending = defer(),
    calls = [];
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    if (path.endsWith('/view')) return f.data;
    return pending.promise;
  };
  await apple.open(f.d);
  await apple.submit(form({ report_id: 'report-1', interval_hours: '23' }), f.d);
  await apple.submit(form({ report_id: 'foreign', interval_hours: '24' }), f.d);
  assert.equal(calls.length, 1);
  const request = apple.submit(form(), f.d);
  f.state.workspace.identity.principal = 'someone-else';
  pending.resolve({ enabled: true, version: 1 });
  await request;
  assert.equal(calls.filter((c) => c.path.endsWith('/view')).length, 1);
});
test('inventory and pause use displayed source and block repeated submissions', async () => {
  const f = fixture(),
    pending = defer(),
    calls = [];
  f.data.schedule = { enabled: true, version: 7, status: 'ENABLED', failures: 0 };
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    if (path.endsWith('/view')) return f.data;
    return pending.promise;
  };
  await apple.open(f.d);
  const request = apple.action(click('inventory'), f.d);
  await apple.action(click('inventory'), f.d);
  assert.equal(calls.filter((c) => c.path.endsWith('/inventory')).length, 1);
  assert.deepEqual(calls.at(-1).body, {
    manifest_version: 2,
    connection_id: 'connection-1',
    connection_version: 3,
  });
  pending.resolve({ job_id: 'queued-1', status: 'QUEUED' });
  await request;
  assert.match(f.node.fields['#apple-analytics-status'].textContent, /queued-1/);
});
test('pause uses the saved schedule version and a closed modal prevents repair actions', async () => {
  const f = fixture(),
    pending = defer(),
    calls = [];
  f.data.schedule = { enabled: true, version: 7, status: 'ENABLED', failures: 0 };
  let setup = 0;
  f.d.connectionSetup = () => setup++;
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    if (path.endsWith('/view')) return f.data;
    return pending.promise;
  };
  await apple.open(f.d);
  const request = apple.action(click('pause'), f.d);
  await apple.action(click('pause'), f.d);
  assert.deepEqual(calls.at(-1).body, { manifest_version: 2, enabled: false, version: 7 });
  assert.equal(calls.filter((c) => c.path.endsWith('/schedule')).length, 1);
  f.dialog.open = false;
  pending.resolve({ enabled: false, version: 8 });
  await request;
  await apple.action(click('setup'), f.d);
  assert.equal(setup, 0);
  assert.equal(calls.filter((c) => c.path.endsWith('/view')).length, 1);
});
test('store impressions queues only the current complete discovery report', async () => {
  const f = fixture(),
    calls = [];
  const discovery = {
    id: 'discovery-1',
    name: 'App Store Discovery and Engagement Standard',
    coverage: 'PARTIAL',
    instance_count: 1,
  };
  f.data.reports.push(discovery);
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    return path.endsWith('/view') ? f.data : { job_id: 'impression-job' };
  };
  await apple.open(f.d);
  assert.doesNotMatch(f.html, /Collect store impressions/);
  await apple.action(click('impressions'), f.d);
  assert.equal(calls.length, 1);
  discovery.coverage = 'COMPLETE';
  await apple.open(f.d);
  assert.match(f.html, /Collect store impressions/);
  assert.match(f.html, /Unique counts can overlap/);
  await apple.action(click('impressions'), f.d);
  assert.deepEqual(calls.at(-1), {
    path: '/api/apps/one/apple-analytics/impressions',
    body: { manifest_version: 2, report_id: 'discovery-1' },
  });
  assert.match(f.node.fields['#apple-analytics-status'].textContent, /impression-job/);
  assert.doesNotMatch(f.html, /<option value="discovery-1"/);
});
test('impression result distinguishes zero from unavailable and labels unique counts at row grain', () => {
  const render = (store_impressions) => apple.impressionsResult({ store_impressions });
  assert.match(render({ sample: [] }), /Impressions are unknown/);
  const result = render({
    impression_rows: 1,
    sample: [
      { date: '2026-10-23', counts: 0, unique_counts: 0, dimensions: { territory: '<US>' } },
    ],
  });
  assert.match(result, /Unique in row/);
  assert.match(result, /&lt;US&gt;/);
  assert.match(result, /<td>0<\/td><td>0<\/td>/);
});
test('inspect latest refresh opens only the saved job while the app and session remain current', async () => {
  const f = fixture(),
    opened = [];
  f.data.schedule = {
    enabled: true,
    version: 2,
    status: 'ENABLED',
    failures: 1,
    last_job: 'refresh-1',
    last_job_status: 'BLOCKED',
  };
  f.d.openJob = (id) => opened.push(id);
  await apple.open(f.d);
  assert.match(f.html, /repair the reported issue/);
  await apple.action(click('job'), f.d);
  assert.deepEqual(opened, ['refresh-1']);
  f.state.app = 'two';
  await apple.action(click('job'), f.d);
  assert.deepEqual(opened, ['refresh-1']);
});

test('fetch the selected OpenSEO project and read back the exact new report before refreshing the plan', async () => {
  const f = fixture();
  const { form, result } = searchFixture(f);
  const calls = [];
  f.d.state.workspace.insights = {
    sources: [
      { id: 'old', provider: 'openseo', status: 'DISCONNECTED' },
      { id: 'current', provider: 'openseo', status: 'CONNECTED' },
    ],
  };
  f.d.uuid = () => 'reading-save-id';
  f.d.api = async (path, body) => {
    calls.push({ path, body });
    if (path.endsWith('/view')) return f.data;
    if (path.endsWith('/web-read'))
      return { status: 'CONNECTED', report_id: 'new-reading', report: { web_evidence: {} } };
    if (path.endsWith('/save-web-evidence')) return { id: 'reading-save-id' };
    return result;
  };
  await apple.open(f.d);
  await apple.submit(form, f.d, 'search');
  assert.match(f.node.fields['#apple-performance-results'].innerHTML, /Fetch OpenSEO search data/);
  await apple.action(click('search-fetch-web'), f.d);
  assert.deepEqual(calls.slice(-3), [
    { path: '/api/apps/one/insights/current/web-read', body: { confirm_read: true } },
    {
      path: '/api/apps/one/insights/current/save-web-evidence',
      body: { id: 'reading-save-id', manifest_version: 2, report_id: 'new-reading' },
    },
    {
      path: '/api/apps/one/apple-analytics/search-review',
      body: { manifest_version: 2, start: '2026-11-13', end: '2026-11-17' },
    },
  ]);
  assert.match(f.node.fields['#apple-performance-status'].textContent, /OpenSEO data fetched/);
});
