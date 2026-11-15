import assert from 'node:assert/strict';
import test from 'node:test';
import { WMMCampaignPlan as plan } from '../mission_control/static/campaign-plan.mjs';

const workspace = {
  app: {
    id: 'sample-one',
    version: 4,
    data: {
      name: 'Sample',
      job: 'Plan a launch',
      audience: 'Solo founders',
      activation: 'First brief',
      currency: 'USD',
      release: 'build-1',
      locale: 'en-US',
      cadence: 'Seven-day decision check',
    },
  },
  records: [{ kind: 'claim' }, { kind: 'asset' }, { kind: 'asset' }, { kind: 'store' }],
  automation: {
    metric: { label: 'Useful activation', value: 'activation_rate' },
    baseline: { status: 'UNAVAILABLE', reason: 'No matching mature cohort' },
    channel: {
      value: 'LinkedIn',
      alternatives: ['YouTube'],
      basis: 'Explicit operator preference',
    },
    cadence: 'Seven-day decision check',
    drafts: {
      experiment: {
        hypothesis: 'Show the brief to solo founders.',
        stop_rule: 'Stop on broken signup.',
      },
      distribution: { channel: 'LinkedIn', destination: 'https://example.test', currency: 'USD' },
      registered_experiment: { rollback_plan: 'Restore build-1 and the prior brief.' },
    },
    learning: { change: 'Validate the first brief' },
  },
  workflow: { next_action: { title: 'Approve one exact post' } },
};

test('a complete plan is ready for review and keeps spend at zero', () => {
  const value = plan.build(workspace, { now: '2026-11-09T12:00:00Z' });
  assert.equal(value.status, 'READY_FOR_REVIEW');
  assert.equal(value.distribution.budget_minor, 0);
  assert.equal(value.distribution.daily_cap_minor, 0);
  assert.equal(value.positioning.hypothesis, 'Show the brief to solo founders.');
  assert.equal(value.objective.metric, 'Useful activation');
  assert.equal(value.measurement.next_action, 'Approve one exact post');
  assert.equal(value.proof.assets, 2);
  assert.deepEqual(value.missing, []);
});

test('missing app facts stay explicit instead of being invented', () => {
  const value = plan.build({ app: { version: 1, data: { name: 'Empty' } } });
  assert.equal(value.status, 'INPUTS_MISSING');
  assert.deepEqual(value.missing, [
    'user job',
    'audience',
    'useful activation',
    'release',
    'locale',
  ]);
  assert.equal(value.distribution.budget_minor, 0);
  assert.equal(value.objective.baseline, 'UNAVAILABLE');
});

test('first-run planning leaves an unspecified currency blank and authorizes zero spend', () => {
  const value = plan.build({
    app: { ...workspace.app, data: { ...workspace.app.data, currency: '' } },
  });
  assert.equal(value.status, 'READY_FOR_REVIEW');
  assert.deepEqual(value.missing, []);
  assert.equal(value.distribution.currency, '');
  assert.equal(value.distribution.budget_minor, 0);
  assert.equal(value.distribution.daily_cap_minor, 0);
  assert.match(plan.markdown(value), /^Budget: 0 \(no spend authorized\)$/m);
});

test('saved proof is counted, not called approved or current', () => {
  const value = plan.build(workspace);
  assert.equal(value.proof.claims, 1);
  assert.equal(value.proof.store, 1);
  assert.ok(
    value.boundaries.some((item) => item.includes('still need current release/locale review')),
  );
});

test('markdown is human-readable and carries the evidence boundary', () => {
  const text = plan.markdown(plan.build(workspace, { now: '2026-11-09T12:00:00Z' }));
  assert.match(text, /^# sample-one campaign plan/m);
  assert.match(text, /Budget: 0 USD \(no spend authorized\)/);
  assert.match(text, /not a provider upload, publication or spend approval/);
  assert.match(text, /Missing inputs\n- None for planning/);
  assert.match(text, /Approve one exact post/);
});
