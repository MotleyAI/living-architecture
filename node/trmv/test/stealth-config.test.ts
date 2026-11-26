// The config resolver: root and stealth config files, and the stealth directories under the git common dir.
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ConfigError, findConfig, stealthDir } from '../src/config/index.js';

const GIT = ['-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'protocol.file.allow=always'];

function git(cwd: string, ...args: string[]): void {
  execFileSync('git', [...GIT, ...args], { cwd, stdio: 'pipe' });
}

function write(path: string, text = 'format: 0.14.0\n'): string {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
  return path;
}

function tmp(): string {
  return realpathSync(mkdtempSync(join(tmpdir(), 'la-stealth-')));
}

function repo(): string {
  const root = join(tmp(), 'repo');
  mkdirSync(root);
  git(root, 'init', '-q', '-b', 'main');
  write(join(root, 'README.md'), 'demo\n');
  git(root, 'add', '-A');
  git(root, 'commit', '-q', '-m', 'init');
  return root;
}

const LA_STEALTH = '.git/living-architecture/living-architecture.yaml';
const TRMV_STEALTH = '.git/trmv/trmv.yaml';

describe('stealthDir', () => {
  it('lives under the common dir', () => {
    const root = repo();
    expect(stealthDir(root, 'la')).toBe(join(root, '.git', 'living-architecture'));
    expect(stealthDir(root, 'trmv')).toBe(join(root, '.git', 'trmv'));
  });

  it('is the repo’s from a subdirectory', () => {
    const root = repo();
    const sub = join(root, 'sub', 'dir');
    mkdirSync(sub, { recursive: true });
    expect(stealthDir(sub, 'la')).toBe(join(root, '.git', 'living-architecture'));
  });

  it('is shared by a linked worktree', () => {
    const root = repo();
    const wt = join(dirname(root), 'wt');
    git(root, 'worktree', 'add', '-q', '-b', 'feat', wt);
    const stealth = write(join(root, LA_STEALTH));
    expect(stealthDir(wt, 'la')).toBe(join(root, '.git', 'living-architecture'));
    expect(findConfig(wt, 'la')).toEqual({ path: stealth, stealth: true });
  });

  it('is a submodule’s own', () => {
    const root = repo();
    const source = join(dirname(root), 'sub-src');
    mkdirSync(source);
    git(source, 'init', '-q', '-b', 'main');
    write(join(source, 's.txt'), 's\n');
    git(source, 'add', '-A');
    git(source, 'commit', '-q', '-m', 'init');
    git(root, 'submodule', 'add', '-q', source, 'sub');
    write(join(root, LA_STEALTH));
    expect(stealthDir(join(root, 'sub'), 'la')).toBe(join(root, '.git', 'modules', 'sub', 'living-architecture'));
    expect(findConfig(join(root, 'sub'), 'la')).toBeNull();
  });

  it('is null outside git', () => {
    const root = tmp();
    const committed = write(join(root, 'living-architecture.yaml'));
    expect(stealthDir(root, 'la')).toBeNull();
    expect(findConfig(root, 'la')).toEqual({ path: committed, stealth: false });
  });
});

describe('findConfig', () => {
  it('finds nothing without a config file', () => {
    const root = repo();
    expect(findConfig(root, 'trmv')).toBeNull();
    expect(findConfig(root, 'la')).toBeNull();
  });

  it.each([
    ['trmv.yaml', 'trmv'],
    ['living-architecture.yaml', 'trmv'],
    [TRMV_STEALTH, 'trmv'],
    [LA_STEALTH, 'trmv'],
    ['living-architecture.yaml', 'la'],
    [LA_STEALTH, 'la'],
  ] as const)('reads %s alone for %s', (rel, pkg) => {
    const root = repo();
    const path = write(join(root, rel));
    expect(findConfig(root, pkg)).toEqual({ path, stealth: rel.startsWith('.git/') });
  });

  it('reads no trmv file for la', () => {
    const root = repo();
    write(join(root, TRMV_STEALTH));
    expect(findConfig(root, 'la')).toBeNull();
  });

  it.each([
    [['living-architecture.yaml', LA_STEALTH]],
    [['trmv.yaml', TRMV_STEALTH]],
    [[TRMV_STEALTH, LA_STEALTH]],
    [['living-architecture.yaml', TRMV_STEALTH, LA_STEALTH]],
  ])('names every file of %j in lookup order', (rels) => {
    for (const pkg of ['trmv', 'la'] as const) {
      const root = repo();
      for (const rel of rels) write(join(root, rel));
      const named = rels.map((rel) => (rel.startsWith('.git/') ? join(root, rel) : rel)).join(', ');
      expect(() => findConfig(root, pkg)).toThrow(ConfigError);
      expect(() => findConfig(root, pkg)).toThrow(`more than one config file applies (${named}); keep one`);
    }
  });

  it('takes a stealth path that is not a regular file for absent', () => {
    const root = repo();
    mkdirSync(join(root, LA_STEALTH), { recursive: true });
    expect(findConfig(root, 'la')).toBeNull();
  });
});
