// la-doctor and the local override: the git-state finding, its placement, the merged consistency checks and the
// ok line's second source. PATH holds only the real git (or a fake one) and, unless dropped, a stub gh.
import { execFileSync } from 'node:child_process';
import { chmodSync, mkdtempSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { whichPath } from '../src/contract/index.js';
import { VERSION } from '../src/index.js';
import { run, tempRepo } from './cli-run.js';

const COMMITTED = 'living-architecture.yaml';
const LOCAL = 'living-architecture.local.yaml';
const TRACKED = `FAIL: ${LOCAL} is tracked by git, but it holds one contributor's overrides; run git rm --cached ${LOCAL} and add it to .gitignore`;
const NOT_IGNORED = `FAIL: ${LOCAL} is not git-ignored; add it to .gitignore`;
const GIT_FAILED = `FAIL: git failed, so whether ${LOCAL} is git-ignored cannot be checked`;
const NO_PLAN_STORE =
  'FAIL: tracker is none and openspec is false, so no plan survives a session reset; set a tracker or openspec: true';
const MISSING_CONFIG = 'FAIL: no living-architecture.yaml at the repo root; run /la:init to onboard this repo';
const REAL_GIT = whichPath('git');

function script(path: string, body: string): void {
  writeFileSync(path, `#!/bin/sh\n${body}`);
  chmodSync(path, 0o755);
}

/** PATH = one dir with the real git (or `fakeGit` as a script) and, when `gh`, a stub gh. */
function isolatePath(options: { fakeGit?: string; gh?: boolean } = {}): void {
  const bin = mkdtempSync(join(tmpdir(), 'la-doctor-bin-'));
  if (options.fakeGit === undefined) symlinkSync(REAL_GIT as string, join(bin, 'git'));
  else script(join(bin, 'git'), options.fakeGit);
  if (options.gh ?? true) script(join(bin, 'gh'), 'exit 0\n');
  vi.stubEnv('PATH', bin);
}

function git(root: string, ...args: string[]): void {
  execFileSync('git', ['-c', 'user.name=t', '-c', 'user.email=t@example.com', ...args], { cwd: root, stdio: 'pipe' });
}

function localRepo(options: { local?: string | null; ignored?: boolean; committed?: string } = {}): string {
  const files: Record<string, string> = {};
  if (options.local !== null) files[LOCAL] = options.local ?? 'tracker: github\n';
  if (options.ignored) files['.gitignore'] = `${LOCAL}\n`;
  if (options.committed !== undefined) files[COMMITTED] = options.committed;
  return tempRepo(files);
}

function doctor(root: string, ...args: string[]): [number, string[]] {
  const result = run(root, 'la-doctor', ['--root', root, ...args]);
  return [result.code, result.out.split('\n').filter((line) => line !== '')];
}

describe('la-doctor with a local file', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('names a git-ignored local file as a second source', () => {
    const root = localRepo({ ignored: true, committed: 'openspec: false\n' });
    isolatePath();
    expect(doctor(root)).toEqual([0, [`ok: la tools ${VERSION}; config from ${COMMITTED} + ${LOCAL}`]]);
  });

  it('adds the local file to the defaults source outside git', () => {
    const root = mkdtempSync(join(tmpdir(), 'la-nogit-'));
    writeFileSync(join(root, LOCAL), 'tracker: github\n');
    isolatePath({ fakeGit: 'exit 128\n' });
    expect(doctor(root)).toEqual([0, [`ok: la tools ${VERSION}; config from defaults (no config file) + ${LOCAL}`]]);
  });

  it('reports a committed local file as tracked', () => {
    const root = localRepo();
    git(root, 'add', LOCAL);
    git(root, 'commit', '-q', '-m', 'init');
    isolatePath();
    expect(doctor(root)).toEqual([1, [TRACKED]]);
  });

  it('reports a staged local file as tracked even when ignored', () => {
    const root = localRepo();
    git(root, 'add', LOCAL);
    writeFileSync(join(root, '.gitignore'), `${LOCAL}\n`);
    isolatePath();
    expect(doctor(root)).toEqual([1, [TRACKED]]);
  });

  it('reports a local file no ignore rule matches', () => {
    const root = localRepo();
    isolatePath();
    expect(doctor(root)).toEqual([1, [NOT_IGNORED]]);
  });

  it('reports a git ls-files failure', () => {
    const root = localRepo();
    writeFileSync(join(root, '.git', 'index'), 'not an index\n');
    isolatePath();
    expect(doctor(root)).toEqual([1, [GIT_FAILED]]);
  });

  it.each([2, 128])('reports a git check-ignore exit %i', (status) => {
    const root = localRepo();
    isolatePath({ fakeGit: `for a in "$@"; do [ "$a" = check-ignore ] && exit ${status}; done\nexit 0\n` });
    expect(doctor(root)).toEqual([1, [GIT_FAILED]]);
  });

  it('runs no local check without a local file', () => {
    const root = localRepo({ local: null });
    isolatePath({ fakeGit: 'exit 128\n' });
    expect(doctor(root)[0]).toBe(0);
  });

  it('places the local finding after consistency and before missing executables', () => {
    const root = localRepo({ local: 'tracker: none\n', committed: 'openspec: false\n' });
    isolatePath({ gh: false });
    expect(doctor(root)).toEqual([1, [NO_PLAN_STORE, NOT_IGNORED, 'FAIL: `gh` not found on PATH']]);
  });

  it('runs the consistency checks on the merged config', () => {
    const root = localRepo({ local: 'tracker: none\n', ignored: true, committed: 'openspec: false\n' });
    isolatePath();
    expect(doctor(root)).toEqual([1, [NO_PLAN_STORE]]);
  });

  it('skips the consistency checks for a local file alone', () => {
    const root = localRepo({ local: 'tracker: none\n', ignored: true });
    isolatePath();
    expect(doctor(root)[0]).toBe(0);
  });

  it('does not count a local file as the required config file', () => {
    const root = localRepo({ ignored: true });
    isolatePath();
    expect(doctor(root, '--require-config')).toEqual([1, [MISSING_CONFIG]]);
  });

  it('validates a local file without a committed file', () => {
    const root = localRepo({ local: 'openspec: false\n', ignored: true });
    isolatePath();
    const [code, lines] = doctor(root);
    expect(code).toBe(1);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatch(/^FAIL: /);
    expect(lines[0]).toContain('openspec');
    expect(lines[0]).toContain(LOCAL);
  });

  it('still validates a local file under --require-config', () => {
    const root = localRepo({ local: 'openspec: false\n', ignored: true });
    isolatePath();
    const [code, lines] = doctor(root, '--require-config');
    expect(code).toBe(1);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toBe(MISSING_CONFIG);
    expect(lines[1]).toContain('openspec');
    expect(lines[1]).toContain(LOCAL);
  });
});
