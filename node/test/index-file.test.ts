// The index.yaml `tsconfig` key: repo-relative, never resolving outside the repo.
import { mkdirSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { ArchCheckError, resolveTsconfig } from '../src/archcheck/index-file.js';

describe('resolveTsconfig', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-index-file-'));
  const repo = join(tmp, 'repo');
  mkdirSync(join(repo, 'config'), { recursive: true });
  symlinkSync('..', join(repo, 'escape'));
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it('an absent key is null', () => {
    expect(resolveTsconfig(repo, undefined)).toBeNull();
  });

  it('a path in the repo is kept as written, existing or not', () => {
    expect(resolveTsconfig(repo, 'config/tsconfig.json')).toBe('config/tsconfig.json');
    expect(resolveTsconfig(repo, 'missing/tsconfig.json')).toBe('missing/tsconfig.json');
  });

  it.each([
    ['/etc/tsconfig.json', "architecture/index.yaml: tsconfig '/etc/tsconfig.json' must be a relative path"],
    ['', "architecture/index.yaml: tsconfig '' must be a relative path"],
    ['../tsconfig.json', "architecture/index.yaml: tsconfig '../tsconfig.json' must not contain '..'"],
    ['escape/tsconfig.json', "architecture/index.yaml: tsconfig 'escape/tsconfig.json' resolves outside the repo"],
  ])('%j is rejected', (value, error) => {
    expect(() => resolveTsconfig(repo, value)).toThrow(ArchCheckError);
    expect(() => resolveTsconfig(repo, value)).toThrow(error);
  });
});
