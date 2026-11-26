// The stealth merge-base baseline: its cache key and the temporary merge-base checkout.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, realpathSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { withMergeBaseCheckout } from '../src/lang/index.js';
import { cacheKey } from '../src/typecheck/index.js';
import { tempRepo } from './cli-run.js';

const KEY = {
  commit: 'a'.repeat(40),
  language: 'python',
  command: 'basedpyright',
  version: '1.2.3',
  fingerprints: new Map([
    ['pyproject.toml', Buffer.from('[project]\n')],
    ['uv.lock', Buffer.from('lock\n')],
  ]),
};

function committedRepo(): { root: string; commit: string } {
  const root = tempRepo({ 'm.py': 'X = 1\n', '.gitignore': '.venv/\n' });
  const git = (...args: string[]) => execFileSync('git', args, { cwd: root, encoding: 'utf8' });
  git('add', '-A');
  git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--no-gpg-sign', '-q', '-m', 'init');
  mkdirSync(join(root, '.venv', 'bin'), { recursive: true });
  return { root, commit: git('rev-parse', 'HEAD').trim() };
}

const worktrees = (root: string) => execFileSync('git', ['worktree', 'list', '--porcelain'], { cwd: root, encoding: 'utf8' });

describe('cacheKey', () => {
  it('is deterministic', () => {
    expect(cacheKey(KEY)).toBe(cacheKey({ ...KEY, fingerprints: new Map(KEY.fingerprints) }));
  });

  it.each([
    ['commit', 'b'.repeat(40)],
    ['language', 'typescript'],
    ['command', 'basedpyright --level error'],
    ['version', '1.2.4'],
    ['fingerprints', new Map([['pyproject.toml', Buffer.from('[project]\n# edited\n')], ['uv.lock', Buffer.from('lock\n')]])],
    ['fingerprints', new Map([['pyproject.toml', Buffer.from('[project]\n')]])],
  ])('changes with %s', (field, value) => {
    expect(cacheKey({ ...KEY, [field]: value })).not.toBe(cacheKey(KEY));
  });

  it('ignores the fingerprint order', () => {
    expect(cacheKey({ ...KEY, fingerprints: new Map([...KEY.fingerprints].reverse()) })).toBe(cacheKey(KEY));
  });
});

describe('withMergeBaseCheckout', () => {
  it('links environment dirs into a checkout outside the repo', () => {
    const { root, commit } = committedRepo();
    withMergeBaseCheckout(root, commit, ['.venv', 'node_modules'], (checkout: string) => {
      expect(readFileSync(join(checkout, 'm.py'), 'utf8')).toBe('X = 1\n');
      expect(realpathSync(join(checkout, '.venv'))).toBe(realpathSync(join(root, '.venv')));
      expect(existsSync(join(checkout, 'node_modules'))).toBe(false);
      expect(relative(realpathSync(root), realpathSync(checkout)).startsWith('..')).toBe(true);
      expect(worktrees(root)).toContain(checkout);
    });
  });

  it('removes and prunes the checkout', () => {
    const { root, commit } = committedRepo();
    let seen = '';
    withMergeBaseCheckout(root, commit, ['.venv'], (checkout: string) => {
      seen = checkout;
    });
    expect(existsSync(seen)).toBe(false);
    expect(worktrees(root)).not.toContain(seen);
  });

  it('removes and prunes the checkout when the callback throws', () => {
    const { root, commit } = committedRepo();
    let seen = '';
    expect(() =>
      withMergeBaseCheckout(root, commit, [], (checkout: string) => {
        seen = checkout;
        throw new Error('boom');
      }),
    ).toThrow('boom');
    expect(existsSync(seen)).toBe(false);
    expect(worktrees(root)).not.toContain(seen);
  });
});
