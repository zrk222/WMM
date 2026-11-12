import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { validate } from '../tools/check_es_modules.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const libraries = [
  ['analytics-inventory', 'WMMAnalyticsInventory'],
  ['campaign-plan', 'WMMCampaignPlan'],
  ['mmp-import-model', 'WMMMmpImport'],
];

test('native libraries export APIs without installing compatibility globals', async () => {
  for (const [file, name] of libraries) {
    assert.equal(Object.hasOwn(globalThis, name), false);
    const module = await import(`../mission_control/static/${file}.mjs`);
    assert.equal(typeof module[name], 'object');
    assert.equal(Object.hasOwn(globalThis, name), false);
    const source = fs.readFileSync(path.join(root, `mission_control/static/${file}.mjs`), 'utf8');
    assert.doesNotMatch(source, /module\.exports|globalThis/);
  }
});

test(
  'maintained checkJs rejects wrong inputs for all three libraries',
  {
    skip:
      !fs.existsSync(path.join(root, 'node_modules/typescript/bin/tsc')) &&
      process.env.WMM_CHECK_JS_TYPES_REQUIRED !== '1'
        ? 'TypeScript negative fixtures run in the mandatory maintainability tooling profile'
        : false,
  },
  () => {
    const folder = fs.mkdtempSync(path.join(root, '.factory-library-types-'));
    try {
      const fixture = path.join(folder, 'negative.mjs');
      fs.writeFileSync(
        fixture,
        `
import { WMMAnalyticsInventory } from '../mission_control/static/analytics-inventory.mjs';
import { WMMCampaignPlan } from '../mission_control/static/campaign-plan.mjs';
import { WMMMmpImport } from '../mission_control/static/mmp-import-model.mjs';
WMMAnalyticsInventory.summary({metrics: {cohorts: 4}});
WMMCampaignPlan.build({app: {version: 'wrong'}});
WMMMmpImport.parseHeaders(123, 'csv');
`,
      );
      const result = spawnSync(
        process.execPath,
        [
          path.join(root, 'node_modules/typescript/bin/tsc'),
          '--allowJs',
          '--checkJs',
          '--noEmit',
          '--strict',
          '--target',
          'ES2022',
          '--module',
          'NodeNext',
          fixture,
        ],
        { cwd: root, encoding: 'utf8' },
      );
      assert.ifError(result.error);
      assert.equal(result.status, 2, result.stdout + result.stderr);
      assert.match(result.stdout, /negative\.mjs\(5,/);
      assert.match(result.stdout, /negative\.mjs\(6,/);
      assert.match(result.stdout, /negative\.mjs\(7,/);
    } finally {
      fs.rmSync(folder, { recursive: true, force: true });
    }
  },
);

test('native graph keeps at most 24 compatibility libraries', () => {
  const staticRoot = path.join(root, 'mission_control/static');
  assert.ok(validate(staticRoot).compatibilityLibraries <= 24);
  const folder = fs.mkdtempSync(path.join(root, '.factory-module-budget-'));
  try {
    const imports = [];
    for (let index = 0; index < 25; index++) {
      fs.writeFileSync(path.join(folder, `legacy-${index}.js`), '');
      imports.push(`import './legacy-${index}.js';`);
    }
    fs.writeFileSync(path.join(folder, 'dashboard.mjs'), imports.join('\n'));
    assert.throws(() => validate(folder), /Compatibility library budget exceeded: 25/);
  } finally {
    fs.rmSync(folder, { recursive: true, force: true });
  }
});
