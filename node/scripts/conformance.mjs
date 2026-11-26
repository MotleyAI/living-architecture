// Run the shared conformance corpus (the Python runner, from each package's suite) with the npm twin's built bins;
// the npm twin invokes unless LA_CONFORMANCE_TWIN says otherwise.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const PYTHON = join(dirname(ROOT), 'python');
// Per package: its Python suite's conformance tests.
const SUITES = { trmv: ['tests/test_conformance.py', 'tests/test_module_map_equivalence.py'], la: ['tests/test_conformance.py'] };
const bins = mkdtempSync(join(tmpdir(), 'la-node-bin-'));
for (const pkg of Object.keys(SUITES)) {
  for (const file of readdirSync(join(ROOT, pkg, 'dist', 'bin'))) {
    symlinkSync(join(ROOT, pkg, 'dist', 'bin', file), join(bins, file.replace(/\.js$/, '')));
  }
}
const env = { LA_CONFORMANCE_TWIN: 'typescript', ...process.env, LA_NODE_BIN_DIR: bins };
let status = 0;
for (const [pkg, tests] of Object.entries(SUITES)) {
  const args = ['run', 'pytest', '-q', ...tests, ...process.argv.slice(2)];
  const proc = spawnSync('uv', args, { cwd: join(PYTHON, pkg), env, stdio: 'inherit' }); // NOSONAR(S4036) — runs the developer's own uv from PATH by design
  // 5: a filter selected none of this suite's tests.
  if (proc.status !== 0 && proc.status !== 5) status = proc.status ?? 1;
}
rmSync(bins, { recursive: true, force: true });
process.exit(status);
