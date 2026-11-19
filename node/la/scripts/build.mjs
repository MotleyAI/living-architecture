// Compile src/ to dist/ against dr's built declarations, copy la's contract snapshot (modes kept), and write one bin per
// la command.
import { execFileSync } from 'node:child_process';
import { chmodSync, cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const DIST = join(ROOT, 'dist');
const TSC = join(dirname(ROOT), 'node_modules', '.bin', 'tsc');
const SNAPSHOT = join(ROOT, 'src', 'contract', 'data');

rmSync(DIST, { recursive: true, force: true });
execFileSync(TSC, ['-p', join(ROOT, 'tsconfig.build.json')], { stdio: 'inherit' });
cpSync(SNAPSHOT, join(DIST, 'contract', 'data'), { recursive: true });
const manifest = parse(readFileSync(join(SNAPSHOT, 'cli.yaml'), 'utf8')).commands;
mkdirSync(join(DIST, 'bin'), { recursive: true });
for (const command of Object.keys(manifest)) {
  const bin = join(DIST, 'bin', `${command}.js`);
  writeFileSync(bin, `#!/usr/bin/env node\nimport { main } from '../cli/index.js';\n\nmain(${JSON.stringify(command)});\n`);
  chmodSync(bin, 0o755);
}
