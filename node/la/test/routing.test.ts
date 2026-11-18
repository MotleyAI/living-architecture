// dr-* directory expansion: excluded directory names count from the repo root down.
import { execFileSync } from 'node:child_process';
import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { refactorLanguage, RoutingError, split } from '../src/refactor/routing.js';

const { listed } = vi.hoisted(() => ({ listed: [] as string[] }));

vi.mock(import('node:fs'), async (importOriginal) => {
  const fs = await importOriginal();
  const readdirSync = ((path: Parameters<typeof fs.readdirSync>[0], options: Parameters<typeof fs.readdirSync>[1]) => {
    listed.push(String(path));
    return fs.readdirSync(path, options);
  }) as typeof fs.readdirSync;
  return { ...fs, readdirSync };
});

const cwd = process.cwd();

function repoUnderNodeModules(): string {
  const repo = join(mkdtempSync(join(tmpdir(), 'la-routing-')), 'node_modules', 'repo');
  const files = { 'tsconfig.json': '{}', 'src/a.ts': 'export {};\n', 'node_modules/dep/b.ts': 'export {};\n' };
  for (const [rel, text] of Object.entries(files)) {
    mkdirSync(dirname(join(repo, rel)), { recursive: true });
    writeFileSync(join(repo, rel), text);
  }
  execFileSync('git', ['init', '-q', '-b', 'main'], { cwd: repo });
  process.chdir(repo);
  return repo;
}

describe('split', () => {
  afterEach(() => process.chdir(cwd));

  it('an excluded ancestor outside the repo does not count', () => {
    const repo = repoUnderNodeModules();
    expect(split('dr-compliance', [join(repo, 'src')])).toEqual(new Map([['typescript', [join(repo, 'src', 'a.ts')]]]));
  });

  it('a requested directory inside an excluded one expands to nothing', () => {
    const repo = repoUnderNodeModules();
    expect(split('dr-compliance', [join(repo, 'node_modules', 'dep')])).toEqual(new Map());
  });

  it('a directory inside an excluded one is not walked', () => {
    const repo = repoUnderNodeModules();
    const dep = join(repo, 'node_modules', 'dep');
    listed.length = 0;
    const dest = join(repo, 'src');
    split('dr-compliance', [dep]);
    expect(() => refactorLanguage('move-module', dep, dest, repo)).toThrow(RoutingError);
    expect(listed.filter((path) => path.startsWith(dep))).toEqual([]);
  });

  it('an unreadable directory is skipped', () => {
    const repo = repoUnderNodeModules();
    const locked = join(repo, 'src', 'locked');
    mkdirSync(locked);
    chmodSync(locked, 0o000);
    try {
      expect(split('dr-compliance', [join(repo, 'src')])).toEqual(new Map([['typescript', [join(repo, 'src', 'a.ts')]]]));
    } finally {
      chmodSync(locked, 0o755);
    }
  });
});
