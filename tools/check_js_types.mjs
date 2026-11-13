/* Check the three maintained native libraries with the local pinned compiler. */
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const result = spawnSync(
  process.execPath,
  [path.join(root, 'node_modules/typescript/bin/tsc'), '--project', 'tsconfig.maintained-js.json'],
  { cwd: root, stdio: 'inherit' },
);
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
