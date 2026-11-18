// Compile src/ to dist/, copy the contract snapshot (modes kept), and write one bin per manifest command.
import { execFileSync } from 'node:child_process';
import { chmodSync, cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const DIST = join(ROOT, 'dist');

rmSync(DIST, { recursive: true, force: true });
execFileSync(join(ROOT, 'node_modules', '.bin', 'tsc'), ['-p', join(ROOT, 'tsconfig.build.json')], { stdio: 'inherit' });
cpSync(join(ROOT, 'src', 'contract', 'data'), join(DIST, 'contract', 'data'), { recursive: true });
const commands = Object.keys(parse(readFileSync(join(ROOT, 'src', 'contract', 'data', 'cli.yaml'), 'utf8')).commands);
mkdirSync(join(DIST, 'bin'), { recursive: true });
for (const command of commands) {
  const bin = join(DIST, 'bin', `${command}.js`);
  writeFileSync(bin, `#!/usr/bin/env node\nimport { main } from '../cli/index.js';\n\nmain(${JSON.stringify(command)});\n`);
  chmodSync(bin, 0o755);
}
