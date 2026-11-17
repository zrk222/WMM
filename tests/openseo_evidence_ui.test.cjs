const test = require('node:test');
const assert = require('node:assert/strict');
const growth = require('../mission_control/static/growth-review.js');

const data = {
  provider: 'openseo',
  website: 'https://example.com',
  territory: 'US',
  locale: 'en-US',
  release: 'r1',
  observations: [{}],
};

function state(rows = []) {
  return {
    app: 'one',
    workspace: {
      app: { id: 'one', version: 1, data: { name: 'Test app' } },
      subscription_growth: {
        app_id: 'one',
        context: { manifest_version: 1 },
        observed_at: 'now',
        history: { history: rows },
        issues: [],
        journeys: [],
        experiments: [],
        evidence_states: {},
      },
    },
  };
}

test('OpenSEO import previews before saving through the app-version-bound route', async () => {
  const input = { text: async () => JSON.stringify(data), size: 100 };
  const preview = { innerHTML: '' };
  const submit = {};
  const form = {
    isConnected: true,
    dataset: { mode: 'web-seo', app: 'one', id: 'seo-test', version: '1' },
    querySelector: (selector) =>
      selector.includes('submit') ? submit : selector.includes('preview') ? preview : {},
  };
  const requests = [];
  const deps = {
    state: state(),
    FormData: class {
      get() {
        return input;
      }
    },
    api: async (...args) => requests.push(args),
    refresh: async () => {},
    close: () => {},
    toast: () => {},
  };
  await growth.submit(form, deps);
  assert.equal(requests.length, 0);
  assert.match(preview.innerHTML, /Review web search evidence/);
  assert.match(preview.innerHTML, /spends nothing/);
  await growth.submit(form, deps);
  assert.equal(requests.length, 1);
  assert.equal(requests[0][0], '/api/apps/one/subscription-growth/entries');
  assert.equal(JSON.parse(requests[0][2].body).kind, 'WEB_SEO_EVIDENCE');
});

test('Web report clears native metrics and retains unknowns and a real zero', () => {
  const row = {
    id: 'saved-web',
    kind: 'WEB_SEO_EVIDENCE',
    data,
    hash: 'source',
    readout: {
      analysis: {
        next_action: 'Test a headline',
        observations: [
          {
            subject: 'Buyer query',
            status: 'REVIEW_ACTION',
            family: 'Search Console',
            coverage: 'COMPLETE',
            values: { clicks: 0, position: null },
            units: { clicks: 'count', position: 'position' },
          },
        ],
      },
    },
  };
  const report = growth.report(
    state([row]),
    {
      model: () => ({
        metrics: [{ label: 'native installs' }],
      }),
    },
    row.id,
  );
  assert.equal(report.title, 'OpenSEO web acquisition report');
  assert.deepEqual(report.metrics, []);
  assert.match(report.notes[0], /provider verification has not run/);
  const facts = Object.fromEntries(report.sections[0].items[0].facts);
  assert.equal(facts['position (position)'], 'Unknown');
  assert.equal(facts['clicks (count)'], '0');
});

test('The exported web report leads with a measurable change and retains source observations', () => {
  const row = {
    id: 'web-test',
    kind: 'WEB_SEO_EVIDENCE',
    data,
    hash: 'source',
    readout: {
      analysis: {
        test_brief: {
          state: 'DRAFT_FOR_REVIEW',
          page: 'https://example.com/guide',
          subject: 'Buyer query',
          territory: 'US',
          device: 'MOBILE',
          change: 'Change the search title',
          hypothesis: 'Match the query',
          baseline: { label: 'Google organic CTR', value: 0, numerator: 0, denominator: 250 },
          baseline_window: { start: '2026-11-01', end: '2026-11-14' },
          comparison_days: 14,
          comparison: 'Use the same window.',
          guardrail: 'Keep the CTA fixed.',
          decision: 'Collect if sample is too small.',
          source_sha256: 'a'.repeat(64),
        },
        observations: [],
      },
    },
  };
  const report = growth.report(state([row]), { model: () => ({}) }, row.id);
  assert.equal(report.executive.primary.value, '0.00% (0 / 250)');
  assert.equal(report.executive.next, 'Review the proposed change: Change the search title');
  assert.equal(report.sections[0].title, 'Next marketing test');
  const facts = Object.fromEntries(report.sections[0].items[0].facts);
  assert.equal(facts['Google organic CTR baseline'], '0.00% (0 / 250)');
  assert.equal(facts['Compare'], '14 days. Use the same window.');
  assert.equal(facts['Evidence SHA-256'], 'a'.repeat(64));
  assert.equal(report.sections[1].title, 'Web SEO observations');
});
