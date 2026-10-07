// dr-* directory expansion: excluded directory names count from the repo root down.
import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { split } from '../src/refactor/routing.js';

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
});
