const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('./helpers/module-source.cjs');
const vm = require('node:vm');
const { join } = require('node:path');
const source = readFileSync(join(__dirname, '../mission_control/static/app-research.mjs'), 'utf8');

function fixture() {
  const notes = { textContent: '' };
  const more = { remove() {} };
  const toolbar = { insertAdjacentHTML() {} };
  const section = {
    querySelector(sel) {
      if (sel.includes('activity-more')) return more;
      return sel === '.toolbar' ? toolbar : notes;
    },
  };
  const list = {
    dataset: {},
    isConnected: true,
    innerHTML: 'Initial records',
    closest: () => section,
    insertAdjacentHTML(_, html) {
      this.innerHTML += html;
    },
  };
  const filter = { value: '' };
  const state = {
    app: 'first',
    view: 'activity',
    workspace: { app: { id: 'first' }, identity: { principal: 'owner' } },
  };
  const reads = [];
  const context = vm.createContext({
    state,
    URLSearchParams,
    $: (selector) => (selector === '#activity-kind' ? filter : list),
    document: { body: {}, activeElement: {} },
    api: (url) => new Promise((resolve, reject) => reads.push({ url, resolve, reject })),
    esc: String,
    label: String,
    button: () => '<button></button>',
    notice: String,
  });
  vm.runInContext(source, context);
  const action = vm.runInContext('activityAction', context);
  return { action, list, filter, state, reads, notes };
}
const row = (id) => ({ action: id, kind: 'AUDIT', at: '2026-11-01T00:00:00Z', receipt: { id } });
const reply = (...ids) => ({ events: ids.map(row), boundary: 'Saved only' });
const control = (cursor) => ({ dataset: { cursor }, disabled: false });

test('a delayed activity response never crosses into another app, owner, view or replaced timeline', async () => {
  for (const change of [
    (h) => {
      h.state.app = 'other';
    },
    (h) => {
      h.state.workspace.identity.principal = 'other';
    },
    (h) => {
      h.state.view = 'overview';
    },
    (h) => {
      h.list.isConnected = false;
    },
    (h) => {
      h.filter.value = 'JOB';
    },
  ]) {
    const h = fixture();
    const pending = h.action(control());
    change(h);
    h.reads[0].resolve(reply('do-not-show'));
    await pending;
    assert.equal(h.list.innerHTML, 'Initial records');
  }
});

test('pagination binds to the applied filter and skips a repeated click while fetching', async () => {
  const h = fixture();
  h.filter.value = 'AUDIT';
  await assert.rejects(h.action(control('older')), /Apply the selected record type/);
  assert.equal(h.reads.length, 0);
  const filtered = h.action(control());
  h.reads[0].resolve(reply('first-page'));
  await filtered;
  const button = control('older');
  const older = h.action(button);
  await h.action(button);
  assert.equal(h.reads.length, 2);
  assert.match(h.reads[1].url, /kind=AUDIT&cursor=older$/);
  h.reads[1].resolve(reply('second-page'));
  await older;
  assert.match(h.list.innerHTML, /first-page.*second-page/s);
  assert.equal(button.disabled, false);
});

test('a new filter wins over older pagination even if the latter fails after the new page opens', async () => {
  const h = fixture();
  const older = h.action(control('older'));
  h.filter.value = 'AUDIT';
  const filtered = h.action(control());
  h.reads[1].resolve(reply('new-result'));
  await filtered;
  h.reads[0].reject(new Error('Old failure'));
  await older;
  assert.match(h.list.innerHTML, /new-result/);
  assert.match(h.notes.textContent, /1 records on this page/);
});
