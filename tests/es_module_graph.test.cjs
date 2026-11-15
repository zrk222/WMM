const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const checker = import('../tools/check_es_modules.mjs');
test('dashboard graph has explicit dependencies and a single entry', async () => {
  const { validate } = await checker;
  const root = path.resolve(__dirname, '../mission_control/static');
  const result = validate(root);
  assert.ok(result.modules >= 45);
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  assert.equal((html.match(/<script\b/g) || []).length, 2);
  assert.match(
    html,
    /<script src="\/startup-recovery.js"><\/script>\s*<script id="workspace-entry" type="module"/,
  );
  assert.match(html, /id="workspace-boot-retry"[^>]+href="\/"/);
  assert.match(html, /type="module" src="\/dashboard.mjs"/);
});
test('missing module and missing named export fail validation', async () => {
  const { validate } = await checker;
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wmm-esm-'));
  try {
    fs.writeFileSync(path.join(root, 'dashboard.mjs'), 'import { value } from "./missing.mjs";\n');
    assert.throws(() => validate(root), /Missing module/);
    fs.writeFileSync(path.join(root, 'missing.mjs'), 'export const other = 1;\n');
    assert.throws(() => validate(root), /does not provide an export named/);
  } finally {
    for (const name of fs.readdirSync(root)) fs.unlinkSync(path.join(root, name));
    fs.rmdirSync(root);
  }
});

test('all static import forms are checked and dynamic imports fail closed', async () => {
  const { validate } = await checker;
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wmm-esm-'));
  try {
    for (const declaration of [
      'import value from "./missing.mjs";',
      '  import value from "./missing.mjs";',
      'const local = 1; import * as value from "./missing.mjs";',
      'import * as value from "./missing.mjs";',
      'const value = import("./missing.mjs");',
      'const value = import /* comment */ ("./missing.mjs");',
      'const value = import // comment\n ("./missing.mjs");',
      'export * from "./missing.mjs";',
      'export { value } from "./missing.mjs";',
    ]) {
      fs.writeFileSync(path.join(root, 'dashboard.mjs'), declaration);
      assert.throws(() => validate(root), /Missing module|Unsupported dynamic import/);
    }
  } finally {
    fs.unlinkSync(path.join(root, 'dashboard.mjs'));
    fs.rmdirSync(root);
  }
});

test('dashboard asset errors retry at most once and leave a manual recovery path', () => {
  const root = path.resolve(__dirname, '../mission_control/static');
  const boot = fs.readFileSync(path.join(root, 'startup-recovery.js'), 'utf8');
  const browserState = new Map();
  let reloads = 0;
  const launch = (privateStorage) => {
    const listeners = new Map();
    const heading = { textContent: 'Opening your workspace' };
    const link = {
      textContent: 'Reload workspace',
      addEventListener: (type, handle) => listeners.set(type, handle),
    };
    vm.runInNewContext(boot, {
      document: {
        readyState: 'complete',
        addEventListener: (type, handle) => listeners.set(type, handle),
        getElementById: (id) =>
          ({
            'workspace-boot-heading': heading,
            'workspace-boot-message': { textContent: '' },
            'workspace-boot-retry': link,
          })[id],
      },
      sessionStorage: privateStorage,
      location: { reload: () => reloads++ },
    });
    return {
      emit: (type, id = 'workspace-entry') => listeners.get(type)({ target: { id } }),
      heading,
      link,
    };
  };
  const storage = {
    getItem: (key) => browserState.get(key),
    setItem: (key, value) => browserState.set(key, value),
    removeItem: (key) => browserState.delete(key),
  };
  const initial = launch(storage);
  initial.emit('error', 'some-other-asset');
  assert.equal(reloads, 0);
  initial.emit('error');
  assert.equal(reloads, 1);
  const second = launch(storage);
  second.emit('error');
  assert.equal(reloads, 1);
  assert.equal(second.heading.textContent, 'Your workspace could not open');
  assert.equal(second.link.textContent, 'Retry loading');
  second.emit('click');
  launch(storage).emit('error');
  assert.equal(reloads, 2);
  launch(storage).emit('load');
  launch(storage).emit('error');
  assert.equal(reloads, 3);
  const restricted = launch({
    getItem: () => {
      throw new Error('no storage');
    },
  });
  restricted.emit('error');
  assert.equal(reloads, 3);
  assert.equal(restricted.link.textContent, 'Retry loading');
});
