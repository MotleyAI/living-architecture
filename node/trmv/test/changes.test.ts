// The git change listing: a path named as the ref is not taken for the ref.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { basePaths, isCommit } from '../src/changes/index.js';
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
