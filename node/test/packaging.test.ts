// The packed npm package carries the built bins, the root README.md and LICENSE, and the contract: `npm pack` a staged
// copy without `dist/` (prepack builds it), install the tarball into a clean global prefix outside the checkout, then run
// its bins from a directory outside any repo.
import { spawnSync, type SpawnSyncReturns } from 'node:child_process';
import {
  chmodSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { currentFormat } from '../src/config/index.js';
import { HASH_FILE, loadYamlFile, NODE_ROOT, readJson, REPO_ROOT, SHARED } from './helpers.js';

const TIMEOUT = 600_000;
const TMP = mkdtempSync(join(tmpdir(), 'la-pack-'));
const PREFIX = join(TMP, 'prefix');
const WORK = join(TMP, 'work');
const FAKE_BIN = join(TMP, 'fakebin');
const GH_LOG = join(TMP, 'gh.log');
const PROBE = join(TMP, 'probe.cjs');
const NODE_BIN = join(TMP, 'nodebin');
const STAGE = join(TMP, 'stage');
const CONFORMANCE = join(REPO_ROOT, 'conformance');
const ROOT_FILES = ['README.md', 'LICENSE'];
let TARBALL = '';

// Preloaded into every node process: logs `start <script>`, and `typescript <script>` at exit if the compiler loaded.
const PROBE_SOURCE = `const { appendFileSync, realpathSync } = require('node:fs');
let script = process.argv[1] ?? '';
try { script = realpathSync(script); } catch {}
appendFileSync(process.env.LA_PROBE_LOG, 'start ' + script + '\\n');
process.on('exit', () => {
  if (Object.keys(require.cache).some((p) => p.includes('/node_modules/typescript/'))) {
    appendFileSync(process.env.LA_PROBE_LOG, 'typescript ' + script + '\\n');
  }
});
`;

function run(cmd: string, args: string[], cwd: string, input = ''): SpawnSyncReturns<string> {
  const env = { ...process.env, PATH: [FAKE_BIN, join(PREFIX, 'bin'), process.env.PATH].join(delimiter), TMPDIR: TMP };
  return spawnSync(cmd, args, { cwd, env, input, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
}

function npm(args: string[], cwd: string): string {
  const proc = run('npm', args, cwd);
  if (proc.status !== 0) throw new Error(`npm ${args.join(' ')} failed:\n${proc.stdout}\n${proc.stderr}`);
  return proc.stdout;
}

beforeAll(() => {
  mkdirSync(WORK);
  mkdirSync(FAKE_BIN);
  writeFileSync(join(FAKE_BIN, 'gh'), `#!/bin/sh\necho "$*" >> '${GH_LOG}'\necho '{"html_url": "u"}'\n`);
  chmodSync(join(FAKE_BIN, 'gh'), 0o755);
  writeFileSync(PROBE, PROBE_SOURCE);
  mkdirSync(NODE_BIN);
  symlinkSync(process.execPath, join(NODE_BIN, 'node'));
  // Pack a staged copy so the checkout stays untouched; without leftovers there, only prepack can supply `dist/` and the
  // root files.
  const staged = join(STAGE, 'node');
  for (const name of ROOT_FILES) cpSync(join(REPO_ROOT, name), join(STAGE, name));
  const skipped = new Set(['node_modules', 'dist', ...ROOT_FILES].map((name) => join(NODE_ROOT, name)));
  cpSync(NODE_ROOT, staged, { recursive: true, filter: (src) => !skipped.has(src) });
  symlinkSync(join(NODE_ROOT, 'node_modules'), join(staged, 'node_modules'));
  const [packed] = JSON.parse(npm(['pack', '--json', '--pack-destination', TMP], staged));
  TARBALL = join(TMP, packed.filename);
  npm(['install', '-g', '--prefix', PREFIX, '--no-audit', '--no-fund', TARBALL], WORK);
}, TIMEOUT);

afterAll(() => rmSync(TMP, { recursive: true, force: true }));

const bin = (command: string): string => join(PREFIX, 'bin', command);

/** Run an installed bin under the probe; `path` replaces PATH when given. */
function probed(command: string, args: string[], cwd: string, path?: string[]) {
  const log = join(mkdtempSync(join(TMP, 'probe-')), 'log');
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PATH: path ? path.join(delimiter) : [FAKE_BIN, join(PREFIX, 'bin'), process.env.PATH].join(delimiter),
    TMPDIR: TMP,
    NODE_OPTIONS: `--require=${PROBE}`,
    LA_PROBE_LOG: log,
  };
  delete env.LA_FORWARDED;
  const proc = spawnSync(bin(command), args, { cwd, env, encoding: 'utf8' });
  const lines = existsSync(log) ? readFileSync(log, 'utf8').trim().split('\n') : [];
  return { proc, lines };
}

describe('packed npm package', () => {
  it('carries dist/bin/<command>.js for every manifest command', () => {
    const listed = spawnSync('tar', ['-tzf', TARBALL], { encoding: 'utf8' });
    expect(listed.status, listed.stderr).toBe(0);
    const entries = new Set(listed.stdout.split('\n'));
    const commands = Object.keys(loadYamlFile(join(SHARED, 'cli.yaml')).commands);
    expect(commands.filter((command) => !entries.has(`package/dist/bin/${command}.js`))).toEqual([]);
  });

  it.each(ROOT_FILES)('carries the root %s', (name) => {
    const unpacked = mkdtempSync(join(TMP, 'unpacked-'));
    expect(spawnSync('tar', ['-xzf', TARBALL, '-C', unpacked]).status).toBe(0);
    const packed = join(unpacked, 'package', name);
    expect(existsSync(packed), `package/${name} is missing`).toBe(true);
    expect(readFileSync(packed).equals(readFileSync(join(REPO_ROOT, name)))).toBe(true);
  });
});

describe('installed npm package', () => {
  it('la-doctor --contract-hash prints the PyPI twin hash', () => {
    const proc = run(join(PREFIX, 'bin', 'la-doctor'), ['--contract-hash'], WORK);
    expect(proc.status, proc.stderr).toBe(0);
    const pypi = readFileSync(join(REPO_ROOT, 'python', 'src', 'living_architecture', 'contract', 'data', HASH_FILE), 'utf8');
    expect(proc.stdout).toBe(pypi);
  });

  it('la-config show loads the contract', () => {
    const proc = run(join(PREFIX, 'bin', 'la-config'), ['show'], WORK);
    expect(proc.status, proc.stderr).toBe(0);
  });

  it('la-arch-migrate merges a legacy model', () => {
    const repo = join(TMP, 'legacy');
    mkdirSync(join(repo, 'architecture', 'model'), { recursive: true });
    writeFileSync(join(repo, 'architecture', 'model', 'm.c4'), 'specification {\n}\nmodel {\n}\n');
    writeFileSync(join(repo, 'living-architecture.yaml'), 'tracker: linear\n');
    const proc = run(bin('la-arch-migrate'), ['--root', repo], WORK);
    expect(proc.status, proc.stderr).toBe(0);
    expect(readFileSync(join(repo, 'architecture', 'model.c4'), 'utf8')).toBe('specification {\n}\nmodel {\n}\n');
    expect(readFileSync(join(repo, 'living-architecture.yaml'), 'utf8')).toBe(`format: ${currentFormat()}\ntracker: linear\n`);
  });

  it('a review shim runs its bundled script', () => {
    const argv = ['--comment-id', '9', '--pr', '3', '--repo', 'o/r'];
    const proc = run(join(PREFIX, 'bin', 'la-reply-to-pr-thread'), argv, WORK, 'body');
    expect(proc.status, proc.stderr).toBe(0);
    expect(proc.stdout).toBe('u\n');
    expect(readFileSync(GH_LOG, 'utf8')).toContain('repos/o/r/pulls/3/comments/9/replies');
  });

  it('conventions facts keep the order of a path list longer than a command line', () => {
    const paths = Array.from({ length: 30_000 }, (_, i) => `web/${'d'.repeat(60)}/${String(30_000 - i).padStart(5, '0')}_${'m'.repeat(40)}.ts`);
    const stdin = JSON.stringify(paths);
    expect(stdin.length).toBeGreaterThan(2 * 1024 * 1024);
    const proc = run(join(PREFIX, 'bin', 'la-check-conventions'), ['--language', 'typescript', '--emit', 'facts'], WORK, stdin);
    expect(proc.status, proc.stderr).toBe(0);
    const files: { path: string; status: string }[] = JSON.parse(proc.stdout).files;
    expect(files.map((f) => f.path)).toEqual(paths);
    expect(new Set(files.map((f) => f.status))).toEqual(new Set(['missing']));
  });
});

describe('installed npm package: TypeScript compiler loading', () => {
  it.each([
    ['la-config', ['--help']],
    ['la-doctor', ['--twin']],
  ])('%s %s does not load typescript', (command, args) => {
    const { proc, lines } = probed(command, args, WORK);
    expect(proc.status, proc.stderr).toBe(0);
    expect(lines).toEqual([`start ${realpathSync(bin(command))}`]);
  });

  it('la-arch-check on a TypeScript repo loads typescript and matches its golden', () => {
    const repo = join(TMP, 'arch-ts');
    for (const overlay of ['repo', 'node']) cpSync(join(CONFORMANCE, 'fixtures', 'arch-ts', overlay), repo, { recursive: true });
    expect(spawnSync('git', ['init', '-q', '-b', 'main'], { cwd: repo }).status).toBe(0);
    const { proc, lines } = probed('la-arch-check', [], repo);
    const golden = join(CONFORMANCE, 'cases', 'arch-check-ts-ok');
    expect({ status: proc.status, stdout: proc.stdout, stderr: proc.stderr }).toEqual({
      status: 0,
      stdout: readFileSync(join(golden, 'stdout'), 'utf8'),
      stderr: readFileSync(join(golden, 'stderr'), 'utf8'),
    });
    expect(lines).toContain(`typescript ${realpathSync(bin('la-arch-check'))}`);
  });
});

describe('installed npm package: forwarding', () => {
  it("does not run the installed package's own la-doctor", () => {
    const stub = join(TMP, 'python-twin');
    const stubLog = join(TMP, 'python-twin.log');
    mkdirSync(stub);
    const hash = readFileSync(join(NODE_ROOT, 'src', 'contract', 'data', HASH_FILE), 'utf8').trim();
    const identity = `python ${readJson(join(NODE_ROOT, 'package.json')).version} ${hash}`;
    writeFileSync(join(stub, 'la-doctor'), `#!/bin/sh\necho "la-doctor $*" >> '${stubLog}'\necho '${identity}'\n`);
    writeFileSync(join(stub, 'dr-refactor'), `#!/bin/sh\necho "dr-refactor $*" >> '${stubLog}'\nexit 7\n`);
    chmodSync(join(stub, 'la-doctor'), 0o755);
    chmodSync(join(stub, 'dr-refactor'), 0o755);
    const args = ['rename', '--file', 'a.py', '--name', 'x', '--new-name', 'y'];
    writeFileSync(join(WORK, 'a.py'), 'x = 1\n');
    const { proc, lines } = probed('dr-refactor', args, WORK, [join(PREFIX, 'bin'), stub, NODE_BIN]);
    expect(proc.status, proc.stderr).toBe(7);
    expect(readFileSync(stubLog, 'utf8').trim().split('\n')).toEqual(['la-doctor --twin', `dr-refactor ${args.join(' ')}`]);
    expect(lines).toContain(`start ${realpathSync(bin('dr-refactor'))}`);
    expect(lines).not.toContain(`start ${realpathSync(bin('la-doctor'))}`);
    expect(lines.filter((line) => line.startsWith('typescript '))).toEqual([]);
  });
});
