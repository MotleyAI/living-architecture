// Run the shared conformance corpus (the Python runner) with the npm twin's built bins; the npm twin invokes
// unless LA_CONFORMANCE_TWIN says otherwise.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const bins = mkdtempSync(join(tmpdir(), 'la-node-bin-'));
for (const file of readdirSync(join(ROOT, 'dist', 'bin'))) {
  symlinkSync(join(ROOT, 'dist', 'bin', file), join(bins, file.replace(/\.js$/, '')));
}
const env = { LA_CONFORMANCE_TWIN: 'typescript', ...process.env, LA_NODE_BIN_DIR: bins };
const args = ['run', 'pytest', '-q', 'tests/test_conformance.py', ...process.argv.slice(2)];
const proc = spawnSync('uv', args, { cwd: join(dirname(ROOT), 'python'), env, stdio: 'inherit' });
rmSync(bins, { recursive: true, force: true });
process.exit(proc.status ?? 1);
