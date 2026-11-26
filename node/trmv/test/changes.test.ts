// The git change listing: a path named as the ref is not taken for the ref.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { basePaths, isCommit, resolveBaseRef } from '../src/changes/index.js';
import { ConfigError } from '../src/config/index.js';
import { tempRepo } from './cli-run.js';

describe('basePaths', () => {
  it('lists the renames since a ref that a tracked file is named as', () => {
    const root = tempRepo({ HEAD: '', 'kept.ts': 'export {};\n' });
    const git = (...args: string[]) => execFileSync('git', args, { cwd: root });
    git('add', '-A');
    git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--no-gpg-sign', '-q', '-m', 'init');
    git('mv', 'kept.ts', 'moved.ts');
    expect([...basePaths('HEAD', root)]).toEqual([['moved.ts', 'kept.ts']]);
  });
});

describe('isCommit', () => {
  it('throws on a git failure instead of taking it for an unknown ref', () => {
    const root = mkdtempSync(join(tmpdir(), 'la-changes-'));
    writeFileSync(join(root, '.git'), 'not a git dir\n');
    expect(() => isCommit('HEAD', root)).toThrow(ConfigError);
  });
});

describe('resolveBaseRef', () => {
  const committed = () => {
    const root = tempRepo({ 'a.ts': 'export {};\n' });
    const git = (...args: string[]) => execFileSync('git', args, { cwd: root, encoding: 'utf8' });
    git('add', '-A');
    git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--no-gpg-sign', '-q', '-m', 'init');
    git('update-ref', 'refs/remotes/origin/main', 'HEAD');
    return { root, git };
  };
  const withUpstream = () => {
    const repo = committed();
    const bare = join(mkdtempSync(join(tmpdir(), 'la-upstream-')), 'upstream.git');
    repo.git('init', '-q', '--bare', bare);
    repo.git('remote', 'add', 'upstream', bare);
    repo.git('push', '-q', 'upstream', 'main');
    return { ...repo, bare };
  };

  it('resolves a plain name on origin', () => {
    expect(resolveBaseRef('main', committed().root)).toBe('origin/main');
  });

  it('resolves a slash branch on origin when no remote has its first segment', () => {
    const { root, git } = committed();
    git('update-ref', 'refs/remotes/origin/feature/x', 'HEAD');
    expect(resolveBaseRef('feature/x', root)).toBe('origin/feature/x');
  });

  it('resolves a remote-tracking base to that remote\'s ref', () => {
    expect(resolveBaseRef('upstream/main', withUpstream().root)).toBe('refs/remotes/upstream/main');
  });

  it('fetches a remote-tracking base from its remote', () => {
    const { root, git, bare } = withUpstream();
    git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--no-gpg-sign', '-q', '--allow-empty', '-m', 'next');
    git('push', '-q', bare, 'HEAD:refs/heads/main');
    resolveBaseRef('upstream/main', root);
    expect(git('rev-parse', 'refs/remotes/upstream/main')).toBe(git('rev-parse', 'HEAD'));
  });

  it('names the remote-tracking ref when it does not resolve', () => {
    expect(() => resolveBaseRef('upstream/nope', withUpstream().root)).toThrow(
      new ConfigError('git rev-parse --verify --quiet refs/remotes/upstream/nope failed'),
    );
  });
});
