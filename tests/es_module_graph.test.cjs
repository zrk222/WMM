const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const checker = import('../tools/check_es_modules.mjs');
test('dashboard graph has explicit dependencies and a single entry', async () => {
  const { validate } = await checker;
  const root = path.resolve(__dirname, '../mission_control/static');
  const result = validate(root);
  assert.ok(result.modules >= 45);
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  assert.equal((html.match(/<script\b/g) || []).length, 1);
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
