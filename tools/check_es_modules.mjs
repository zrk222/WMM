/* Link dashboard modules with Node's native parser without executing application code. */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const linker = String.raw`
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root = path.resolve(process.argv[1]), entry = process.argv[2], cache = new Map();
function read(file) {
  if (!file.startsWith(root + path.sep)) throw new Error('Module escapes static root');
  if (cache.has(file)) return cache.get(file);
  if (!fs.existsSync(file)) throw new Error('Missing module: ' + file);
  const source = fs.readFileSync(file, 'utf8');
  if (file.endsWith('.mjs') && /\bimport(?:\s|\/\*[\s\S]*?\*\/|\/\/[^\r\n]*(?:\r?\n|$))*\(/.test(source))
    throw new Error('Unsupported dynamic import: ' + file);
  const module = new vm.SourceTextModule(source, { identifier: file });
  cache.set(file, module);
  return module;
}
read(path.resolve(root, entry)).link((specifier, parent) => {
  if (!specifier.startsWith('./')) throw new Error('Only declared relative imports are allowed');
  return read(path.resolve(path.dirname(parent.identifier), specifier));
}).then(() => console.log(JSON.stringify({
  modules: [...cache.keys()].filter(file => file.endsWith('.mjs')).length,
  compatibilityLibraries: [...cache.keys()].filter(file => file.endsWith('.js')).length,
}))).catch(error => { console.error(error.message); process.exitCode = 1; });
`;

function validate(root, entry = 'dashboard.mjs') {
  const result = spawnSync(process.execPath,
    ['--experimental-vm-modules', '-e', linker, path.resolve(root), entry],
    { encoding: 'utf8', timeout: 30000, maxBuffer: 1024 * 1024 });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error('Module linkage failed: ' + result.stderr);
  return JSON.parse(result.stdout);
}

export { validate };
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = fileURLToPath(new URL('../mission_control/static', import.meta.url));
  console.log(JSON.stringify({ status: 'PASS', ...validate(root) }));
}
