// la-typecheck with the real tsc, repo-local, through the built bin (run `npm run build` first).
import { spawnSync, type SpawnSyncReturns } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { NODE_ROOT } from './helpers.js';

const BIN = join(NODE_ROOT, 'dist', 'bin', 'la-typecheck.js');
const REPO = join(mkdtempSync(join(tmpdir(), 'la-typecheck-')), 'repo');

function typecheck(...args: string[]): SpawnSyncReturns<string> {
  return spawnSync(process.execPath, [BIN, ...args], { cwd: REPO, encoding: 'utf8' });
}

beforeAll(() => {
  expect(existsSync(BIN), `${BIN} is missing; run npm run build`).toBe(true);
  mkdirSync(join(REPO, 'src'), { recursive: true });
  mkdirSync(join(REPO, 'node_modules', '.bin'), { recursive: true });
  symlinkSync(join(NODE_ROOT, 'node_modules', '.bin', 'tsc'), join(REPO, 'node_modules', '.bin', 'tsc'));
  writeFileSync(join(REPO, 'tsconfig.json'), '{"compilerOptions": {"strict": true, "noEmit": true}, "include": ["src"]}\n');
  writeFileSync(join(REPO, 'src', 'a.ts'), 'export const a: number = "x";\n');
  spawnSync('git', ['init', '-q', '-b', 'main'], { cwd: REPO });
});

afterAll(() => rmSync(join(REPO, '..'), { recursive: true, force: true }));

describe('la-typecheck with the real tsc', () => {
  it('writes, holds and ratchets the baseline', () => {
    const written = typecheck('--write-baseline');
    expect(written.status, written.stdout + written.stderr).toBe(0);
    const baseline = JSON.parse(readFileSync(join(REPO, '.tsc-baseline.json'), 'utf8'));
    expect(Object.keys(baseline.files)).toEqual(['src/a.ts']);

    const rerun = typecheck();
    expect(rerun.status, rerun.stdout + rerun.stderr).toBe(0);

    writeFileSync(join(REPO, 'src', 'a.ts'), 'export const a: number = "x";\nexport const b: string = 1;\n');
    const fresh = typecheck();
    expect(fresh.status, fresh.stdout + fresh.stderr).toBe(1);
    expect(fresh.stdout).toContain('src/a.ts(2,');
  });
});
