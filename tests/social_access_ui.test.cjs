const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('./helpers/module-source.cjs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '../mission_control/static/social-access.mjs'),
  'utf8',
);

function fixture() {
  const account = {
    id: 'account-one',
    version: 2,
    provider: 'facebook',
    status: 'CONNECTED_READ_TESTED',
    reconnect_required: false,
    data: {
      destination: { id: 'page-one', name: '<Sample Page>', kind: 'PAGE' },
      facts: { renewal: 'OFFICIAL_REAUTHORIZATION' },
      last_read_at: '2026-11-04T00:30:02Z',
    },
  };
  const feedback = { textContent: '' },
    repair = { hidden: true };
  const panel = {
    isConnected: true,
    querySelector: (selector) => (selector === '[data-social-feedback]' ? feedback : repair),
  };
  const calls = [],
    events = [];
  const context = {
    state: {
      app: 'sample-one',
      workspace: {
        social_access: {
          accounts: [account],
          setup: {
            configurations: [{ provider: 'facebook' }],
            providers: { facebook: { name: 'Facebook' } },
          },
        },
      },
    },
    esc: (value) =>
      String(value).replace(
        /[&<>"']/g,
        (char) =>
          ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
          })[char],
      ),
    label: (value) => value,
    button: (title, action, attrs = '') =>
      `<button data-action="${action}" ${attrs}>${title}</button>`,
    api: async (url, body) => {
      calls.push({ url, body });
      return {};
    },
    refresh: async () => events.push('refresh'),
    toast: (message) => events.push(message),
    $: () => ({ close: () => events.push('close') }),
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const node = { dataset: { action: 'social-test', id: account.id }, closest: () => panel };
  return { context, account, node, feedback, repair, panel, calls, events };
}

function setupForm(h) {
  const modal = { open: true };
  const error = { textContent: '' };
  const submit = { disabled: false };
  const form = {
    id: 'social-setup-form',
    isConnected: true,
    dataset: { app: 'sample-one', provider: 'facebook', version: '0' },
    elements: { client_secret: { value: 'synthetic-secret' } },
    querySelector: (selector) => (selector === '#social-error' ? error : submit),
  };
  h.context.FormData = class {
    *[Symbol.iterator]() {
      yield ['client_id', '123456'];
    }
  };
  h.context.$ = () => modal;
  return { form, modal, error, submit };
}

test('saved setup offers a safe retry, and an inactive setup never starts consent', async () => {
  for (const change of ['none', 'app', 'closed', 'detached']) {
    const h = fixture();
    const { form, modal, error, submit } = setupForm(h);
    h.context.refresh = async () => {
      h.context.state.workspace.social_access.setup.configurations[0].version = 1;
      if (change === 'app') h.context.state.app = 'sample-two';
      if (change === 'closed') modal.open = false;
      if (change === 'detached') form.isConnected = false;
    };
    h.context.api = async (url, body) => {
      h.calls.push(url);
      if (url.endsWith('/start')) {
        assert.equal(body.version, 1);
        throw new Error('Free local port 8765, then reopen WMM.');
      }
      assert.equal(h.calls.length, 1, 'configuration must not be re-saved after a login failure');
      return { provider: 'facebook', version: 1 };
    };
    await h.context.socialSubmit(form);
    assert.equal(form.elements.client_secret.value, '');
    await h.context.socialSubmit(form);
    assert.equal(submit.disabled, true);
    assert.deepEqual(
      h.calls,
      change !== 'none'
        ? ['/api/apps/sample-one/social-access/save']
        : ['/api/apps/sample-one/social-access/save', '/api/apps/sample-one/social-access/start'],
    );
    if (change === 'none') {
      assert.match(
        error.textContent,
        /Free local port 8765.*Developer setup was saved.*Connect an account/,
      );
      await assert.rejects(h.context.socialSetup('facebook'), /Free local port 8765/);
      assert.equal(h.calls.at(-1), '/api/apps/sample-one/social-access/start');
    } else assert.equal(error.textContent, '');
  }
});

test('late consent response cancels only its own flow after the setup form closes or is replaced', async () => {
  for (const change of ['closed', 'replaced']) {
    const h = fixture();
    const { form, modal } = setupForm(h);
    let complete, started;
    const pending = new Promise((resolve) => {
      complete = resolve;
    });
    const entered = new Promise((resolve) => {
      started = resolve;
    });
    h.context.modal = () => assert.fail('an abandoned form must not open consent');
    h.context.api = async (url, body) => {
      h.calls.push(url);
      if (url.endsWith('/save')) return { provider: 'facebook', version: 1 };
      if (url.endsWith('/start')) {
        started();
        return pending;
      }
      assert.equal(body.flow_id, 'unpresented-flow');
      return {};
    };
    const submitted = h.context.socialSubmit(form);
    await entered;
    if (change === 'closed') modal.open = false;
    else form.isConnected = false;
    complete({ flow_id: 'unpresented-flow' });
    await submitted;
    assert.deepEqual(
      h.calls,
      ['save', 'start', 'cancel'].map((action) => `/api/apps/sample-one/social-access/${action}`),
    );
  }
});

test('direct callback repair displays the current canonical address instead of the saved old port', async () => {
  const h = fixture();
  h.context.state.workspace.social_access.setup.configurations = [
    {
      provider: 'tiktok',
      version: 1,
      data: { redirect_uri: 'http://127.0.0.1:63000/social/callback/tiktok' },
    },
  ];
  h.context.api = async () => ({
    steps: [],
    redirect_needed: 'EXACT_LOOPBACK',
    redirect_uri: 'http://127.0.0.1:8765/social/callback/tiktok',
  });
  let html;
  h.context.$ = () => ({ elements: { campaign_access: { addEventListener() {} } } });
  h.context.modal = (title, content) => {
    html = content;
  };
  await h.context.socialSetup('tiktok', true);
  assert.match(html, /value="http:\/\/127\.0\.0\.1:8765\/social\/callback\/tiktok"/);
  assert.doesNotMatch(html, /63000/);
});

test('saved account shows its historical verification date without making a provider request', () => {
  const h = fixture();
  const html = h.context.socialPanel();
  assert.match(html, /Recorded status: CONNECTED_READ_TESTED/);
  assert.match(html, /Last provider check: 2026-11-04T00:30:02.000Z/);
  assert.match(html, /Test saved access to verify this workstation now/);
  assert.match(html, /Use Edit setup to restore developer credentials/);
  assert.match(html, /&lt;Sample Page&gt;/);
  assert.doesNotMatch(html, /<Sample Page>/);
  assert.equal(h.calls.length, 0);
});

test('missing or invalid historical dates ask for verification and are never inserted into markup', () => {
  const h = fixture();
  for (const stamp of [undefined, '', '<img src=x onerror=alert(1)>']) {
    h.account.data.last_read_at = stamp;
    const html = h.context.socialPanel();
    assert.match(html, /No dated provider check is recorded/);
    assert.doesNotMatch(html, /<img/);
  }
});

test('missing protected credentials keep the account visible with inline repair actions', async () => {
  const h = fixture();
  h.context.api = async (url, body) => {
    h.calls.push({ url, body });
    throw new Error('Protected social credentials are unavailable; reconnect this account');
  };
  await h.context.socialAction(h.node);
  assert.match(h.feedback.textContent, /Protected social credentials are unavailable/);
  assert.equal(h.repair.hidden, false);
  assert.match(h.context.socialPanel(), /data-action="social-edit" data-provider="facebook"/);
  assert.equal(h.account.status, 'CONNECTED_READ_TESTED');
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [
    {
      url: '/api/apps/sample-one/social-access/account-one/test',
      body: { version: 2 },
    },
  ]);
  assert.deepEqual(h.events, []);
});

test('unavailable vault and provider failures display the exact safe error without asking for credential replacement', async () => {
  const h = fixture();
  h.context.api = async () => {
    throw new Error('Windows credential store is unavailable; reconnect when unlocked');
  };
  await h.context.socialAction(h.node);
  assert.match(h.feedback.textContent, /when unlocked/);
  assert.equal(h.repair.hidden, true);
  h.context.api = async () => {
    throw new Error('<Provider temporarily unavailable>');
  };
  await h.context.socialAction(h.node);
  assert.equal(h.feedback.textContent, '<Provider temporarily unavailable>');
  assert.equal(h.repair.hidden, true);
});

test('a successful explicit retry clears the failure, refreshes status and does not publish', async () => {
  const h = fixture();
  h.feedback.textContent = 'Old failure';
  h.repair.hidden = false;
  await h.context.socialAction(h.node);
  assert.equal(h.feedback.textContent, '');
  assert.equal(h.repair.hidden, true);
  assert.equal(h.calls.length, 1);
  assert.match(h.calls[0].url, /\/test$/);
  assert.deepEqual(h.events, [
    'close',
    'refresh',
    'Saved provider read succeeded. Posting remains disabled.',
  ]);
});

test('late failures cannot populate another app or a detached account panel', async () => {
  for (const change of ['app', 'panel']) {
    const h = fixture();
    let reject;
    h.context.api = () =>
      new Promise((resolve, fail) => {
        reject = fail;
      });
    const pending = h.context.socialAction(h.node);
    if (change === 'app') h.context.state.app = 'sample-two';
    else h.panel.isConnected = false;
    reject(new Error('Protected social credentials are unavailable'));
    await pending;
    assert.equal(h.feedback.textContent, '');
    assert.equal(h.repair.hidden, true);
    assert.deepEqual(h.events, []);
  }
});
