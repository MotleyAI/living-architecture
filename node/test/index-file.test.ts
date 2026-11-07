// The index.yaml `tsconfig` key: repo-relative, never resolving outside the repo.
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { ArchCheckError, loadIndex, resolveLayout, resolveTsconfig } from '../src/archcheck/index-file.js';

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

describe('resolveLayout root_packages', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-multi-root-'));
  const repo = join(tmp, 'repo');
  mkdirSync(join(repo, 'src', 'app'), { recursive: true });
  mkdirSync(join(repo, 'src', 'shared'), { recursive: true });
  mkdirSync(join(repo, 'src', 'app', 'nested'), { recursive: true });
  symlinkSync(tmp, join(repo, 'src', 'escape'));
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it('accepts multiple disjoint directories and keeps sourceRoot-relative names', () => {
    expect(resolveLayout(repo, { source_root: 'src', root_packages: ['app', 'shared'] })).toEqual({
      repoRoot: repo,
      sourceRoot: join(repo, 'src'),
      rootPackages: ['app', 'shared'],
      rootPackage: 'app',
    });
  });

  it.each([
    [['app', 'app'], "architecture/index.yaml: root_packages entries 'app' and 'app' overlap"],
    [['app', 'app/nested'], "architecture/index.yaml: root_packages entries 'app' and 'app/nested' overlap"],
    [['app/'], "architecture/index.yaml: root_packages 'app/' must not have empty or '.' segments"],
    [['escape'], "architecture/index.yaml: root_packages entry 'escape' resolves outside source_root 'src'"],
    [['missing'], "architecture/index.yaml: root_packages entry 'missing' is not a directory under source_root 'src'"],
  ])('rejects invalid roots %j', (rootPackages, error) => {
    expect(() => resolveLayout(repo, { source_root: 'src', root_packages: rootPackages })).toThrow(ArchCheckError);
    expect(() => resolveLayout(repo, { source_root: 'src', root_packages: rootPackages })).toThrow(error);
  });

  it.each([{ roots: 'app' }, { roots: ['app', 42] }, { roots: [] }])('rejects malformed root_packages $roots', ({ roots }) => {
    expect(() => resolveLayout(repo, { source_root: 'src', root_packages: roots })).toThrow(ArchCheckError);
    expect(() => resolveLayout(repo, { source_root: 'src', root_packages: roots })).toThrow(
      'architecture/index.yaml: root_packages must be a non-empty list of strings',
    );
  });
});

describe('loadIndex root configuration', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-index-roots-'));
  const repo = join(tmp, 'repo');
  mkdirSync(join(repo, 'architecture'), { recursive: true });
  mkdirSync(join(repo, 'src', 'app'), { recursive: true });
  mkdirSync(join(repo, 'src', 'shared'), { recursive: true });
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it('accepts root_packages in the shared index schema', () => {
    writeFileSync(join(repo, 'architecture', 'index.yaml'), 'typescript:\n  source_root: src\n  root_packages: [app, shared]\n');
    expect(loadIndex(repo).has('typescript')).toBe(true);
  });

  it('rejects both root configuration forms', () => {
    writeFileSync(join(repo, 'architecture', 'index.yaml'), 'typescript:\n  root_package: src\n  root_packages: [src]\n');
    expect(() => loadIndex(repo)).toThrow('set exactly one of root_package or root_packages');
  });

  it('rejects empty and duplicate root lists through the shared schema', () => {
    writeFileSync(join(repo, 'architecture', 'index.yaml'), 'typescript:\n  root_packages: []\n');
    expect(() => loadIndex(repo)).toThrow(/root_packages/);
    writeFileSync(join(repo, 'architecture', 'index.yaml'), 'typescript:\n  root_packages: [src, src]\n');
    expect(() => loadIndex(repo)).toThrow(/root_packages/);
  });

  it.each(['app', '[app, 42]', '[]'])('rejects malformed root_packages %s with the shared finding', (rootPackages) => {
    writeFileSync(join(repo, 'architecture', 'index.yaml'), `typescript:\n  root_packages: ${rootPackages}\n`);
    expect(() => loadIndex(repo)).toThrow('architecture/index.yaml: root_packages must be a non-empty list of strings');
  });
});
