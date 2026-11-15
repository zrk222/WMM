/* Existing isolated-function VM tests use injected services, not ESM linking.
 * The real import graph is separately tested in Chromium and graph tests.
 */
const fs = require('node:fs');
module.exports = {
  ...fs,
  readFileSync(file, options) {
    const result = fs.readFileSync(file, options);
    if (!String(file).endsWith('.mjs') || typeof result !== 'string') return result;
    return result.replace('const WMMPublicationUI =', 'window.WMMPublicationUI =').replace(/^import[\s\S]*?;\r?\n/gm, '')
      .replace(/^export\s*\{[^}]+\};?\s*$/gm, '');
  },
};
