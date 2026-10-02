// The packed npm package carries the contract: `npm run build`, `npm pack`, install the tarball into a clean global
// prefix outside the checkout, then run its bins from a directory outside any repo.
import { spawnSync, type SpawnSyncReturns } from 'node:child_process';
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { HASH_FILE, NODE_ROOT, REPO_ROOT } from './helpers.js';

const TIMEOUT = 600_000;
const TMP = mkdtempSync(join(tmpdir(), 'la-pack-'));
const PREFIX = join(TMP, 'prefix');
const WORK = join(TMP, 'work');
const FAKE_BIN = join(TMP, 'fakebin');
const GH_LOG = join(TMP, 'gh.log');

function run(cmd: string, args: string[], cwd: string, input = ''): SpawnSyncReturns<string> {
  const env = { ...process.env, PATH: [FAKE_BIN, join(PREFIX, 'bin'), process.env.PATH].join(delimiter), TMPDIR: TMP };
  return spawnSync(cmd, args, { cwd, env, input, encoding: 'utf8' });
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
  npm(['run', 'build'], NODE_ROOT);
  const [packed] = JSON.parse(npm(['pack', '--json', '--pack-destination', TMP], NODE_ROOT));
  npm(['install', '-g', '--prefix', PREFIX, '--no-audit', '--no-fund', join(TMP, packed.filename)], WORK);
}, TIMEOUT);

afterAll(() => rmSync(TMP, { recursive: true, force: true }));

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

  it('a review shim runs its bundled script', () => {
    const argv = ['--comment-id', '9', '--pr', '3', '--repo', 'o/r'];
    const proc = run(join(PREFIX, 'bin', 'la-reply-to-pr-thread'), argv, WORK, 'body');
    expect(proc.status, proc.stderr).toBe(0);
    expect(proc.stdout).toBe('u\n');
    expect(readFileSync(GH_LOG, 'utf8')).toContain('repos/o/r/pulls/3/comments/9/replies');
  });
});
