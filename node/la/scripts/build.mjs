// Compile src/ to dist/ against dr's built declarations, and write one bin per la command.
import { execFileSync } from 'node:child_process';
import { chmodSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const DIST = join(ROOT, 'dist');
const TSC = join(dirname(ROOT), 'node_modules', '.bin', 'tsc');
const MANIFEST = join(dirname(ROOT), 'dr', 'src', 'contract', 'data', 'cli.yaml');

rmSync(DIST, { recursive: true, force: true });
execFileSync(TSC, ['-p', join(ROOT, 'tsconfig.build.json')], { stdio: 'inherit' });
const manifest = parse(readFileSync(MANIFEST, 'utf8')).commands;
mkdirSync(join(DIST, 'bin'), { recursive: true });
for (const command of Object.keys(manifest).filter((name) => name.startsWith('la-'))) {
  const bin = join(DIST, 'bin', `${command}.js`);
  writeFileSync(bin, `#!/usr/bin/env node\nimport { main } from '../cli/index.js';\n\nmain(${JSON.stringify(command)});\n`);
  chmodSync(bin, 0o755);
}
