// Every trmv-refactor subcommand keeps .tsc-baseline.json aligned, in dry-run and apply alike.
import { describe, expect, it, vi } from 'vitest';
import { message } from '../src/contract/index.js';
import { expectedOut, files, read, refactor, renameHeader, tscBaseline, tsProject } from './refactor-project.js';

const { reads } = vi.hoisted(() => ({ reads: [] as string[] }));

vi.mock(import('node:fs'), async (importOriginal) => {
  const fs = await importOriginal();
  const readFileSync = ((path: Parameters<typeof fs.readFileSync>[0], options?: Parameters<typeof fs.readFileSync>[1]) => {
    reads.push(String(path));
    return fs.readFileSync(path, options);
  }) as typeof fs.readFileSync;
  return { ...fs, readFileSync };
});

const CONFIG = 'commands:\n  typecheck:\n    typescript: tsc --noEmit\n';
const A = 'export interface Old {\n  x: number;\n}\n\nexport function make(): Old {\n  return { x: 1 };\n}\n';
const A_NEW = A.replaceAll('Old', 'New');
// Unedited by the rename: its TS2322 message names the type.
const C = "import { make } from './a';\n\nexport const n: number = make();\n";
const named = (type: string): string => `Type '${type}' is not assignable to type 'number'.`;
const OLD_BASELINE = tscBaseline([['src/c.ts', 'TS2322', named('Old'), 1]]);
const NEW_BASELINE = tscBaseline([['src/c.ts', 'TS2322', named('New'), 1]]);

const renameOld = (root: string, apply: boolean) =>
  refactor(root, ...(apply ? ['--apply'] : []), 'rename', '--file', 'src/a.ts', '--symbol', 'Old', '--new-name', 'New');

describe('TypeScript baseline alignment', () => {
  it('moves a key whose message names the renamed symbol', () => {
    const root = tsProject({ 'src/a.ts': A, 'src/c.ts': C, '.tsc-baseline.json': OLD_BASELINE }, CONFIG);
    const changes = [{ path: '.tsc-baseline.json', old: OLD_BASELINE, new: NEW_BASELINE }, { path: 'src/a.ts', old: A, new: A_NEW }];
    expect(renameOld(root, true)).toEqual({ code: 0, out: expectedOut([renameHeader('Old', 'New')], changes, true), err: '' });
    expect(read(root, '.tsc-baseline.json')).toBe(NEW_BASELINE);
    expect(read(root, 'src/c.ts')).toBe(C);
  });

  it('aligns from one read of the baseline, whose text the writer re-checks', () => {
    const root = tsProject({ 'src/a.ts': A, 'src/c.ts': C, '.tsc-baseline.json': OLD_BASELINE }, CONFIG);
    reads.length = 0;
    expect(renameOld(root, true).code).toBe(0);
    // One read to align, one by the writer's re-check before writing.
    expect(reads.filter((path) => path.endsWith('.tsc-baseline.json'))).toHaveLength(2);
  });

  it('a dry-run prints the baseline diff with the sources and writes nothing', () => {
    const root = tsProject({ 'src/a.ts': A, 'src/c.ts': C, '.tsc-baseline.json': OLD_BASELINE }, CONFIG);
    const before = files(root);
    const changes = [{ path: '.tsc-baseline.json', old: OLD_BASELINE, new: NEW_BASELINE }, { path: 'src/a.ts', old: A, new: A_NEW }];
    expect(renameOld(root, false)).toEqual({ code: 0, out: expectedOut([renameHeader('Old', 'New')], changes, false), err: '' });
    expect(files(root)).toEqual(before);
  });

  it('leaves a key whose instances split while only one is baselined, with a warning', () => {
    const b = 'export interface Old {\n  y: number;\n}\n\nexport function other(): Old {\n  return { y: 1 };\n}\n';
    const c = "import { make } from './a';\nimport { other } from './b';\n\nexport const n: number = make();\nexport const m: number = other();\n";
    const root = tsProject({ 'src/a.ts': A, 'src/b.ts': b, 'src/c.ts': c, '.tsc-baseline.json': OLD_BASELINE }, CONFIG);
    const result = renameOld(root, true);
    expect(result.code).toBe(0);
    expect(result.err).toBe(`${message('refactor.baseline-ambiguous', { baseline: '.tsc-baseline.json', code: 'TS2322', path: 'src/c.ts' })}\n`);
    expect(read(root, '.tsc-baseline.json')).toBe(OLD_BASELINE);
    expect(read(root, 'src/a.ts')).toBe(A_NEW);
  });

  it('a key of an unedited message stays', () => {
    const baseline = tscBaseline([['src/c.ts', 'TS2322', named('Old'), 1], ['src/d.ts', 'TS2322', "Type 'string' is not assignable to type 'number'.", 1]]);
    const root = tsProject({ 'src/a.ts': A, 'src/c.ts': C, 'src/d.ts': "export const d: number = 'x';\n", '.tsc-baseline.json': baseline }, CONFIG);
    expect(renameOld(root, true).code).toBe(0);
    expect(read(root, '.tsc-baseline.json')).toBe(
      tscBaseline([['src/c.ts', 'TS2322', named('New'), 1], ['src/d.ts', 'TS2322', "Type 'string' is not assignable to type 'number'.", 1]]),
    );
  });

  it('move-module lists the moved files under their new paths', () => {
    const fmt = "export const bad: number = 'x';\n";
    const msg = "Type 'string' is not assignable to type 'number'.";
    const baseline = tscBaseline([['src/util/fmt.ts', 'TS2322', msg, 1]]);
    const root = tsProject({ 'src/util/fmt.ts': fmt, 'src/main.ts': "import { bad } from './util/fmt';\n\nexport const shown = bad;\n", 'src/lib/keep.ts': 'export {};\n', '.tsc-baseline.json': baseline }, CONFIG);
    const result = refactor(root, '--apply', 'move-module', '--module', 'src/util', '--dest', 'src/lib');
    expect(result.code).toBe(0);
    expect(result.out).toContain('--- a/.tsc-baseline.json\n');
    expect(read(root, '.tsc-baseline.json')).toBe(tscBaseline([['src/lib/util/fmt.ts', 'TS2322', msg, 1]]));
  });

  it('move-module follows a diagnostic that depends on a module moved with it', () => {
    const msg = "Type 'string' is not assignable to type 'number'.";
    const use = "import type { T } from './types';\n\nexport const x: T = { a: 'no' };\n";
    const project = { 'src/util/types.ts': 'export type T = { a: number };\n', 'src/util/use.ts': use, 'src/lib/keep.ts': 'export {};\n' };
    const root = tsProject({ ...project, '.tsc-baseline.json': tscBaseline([['src/util/use.ts', 'TS2322', msg, 1]]) }, CONFIG);
    const result = refactor(root, '--apply', 'move-module', '--module', 'src/util', '--dest', 'src/lib');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, '.tsc-baseline.json')).toBe(tscBaseline([['src/lib/util/use.ts', 'TS2322', msg, 1]]));
  });

  it('move-symbol moves the entry of the moved declaration into the destination', () => {
    const msg = "Type 'string' is not assignable to type 'number'.";
    const other = "Type 'number' is not assignable to type 'string'.";
    const a = "export function broken(): number {\n  const v: number = 'x';\n  return v;\n}\n\nexport const keep = 1;\n";
    const b = "export const s: string = 1;\n";
    const baseline = tscBaseline([['src/a.ts', 'TS2322', msg, 1], ['src/b.ts', 'TS2322', other, 1]]);
    const root = tsProject({ 'src/a.ts': a, 'src/b.ts': b, '.tsc-baseline.json': baseline }, CONFIG);
    const result = refactor(root, '--apply', 'move-symbol', '--file', 'src/a.ts', '--symbol', 'broken', '--dest', 'src/b.ts');
    expect(result.code).toBe(0);
    expect(read(root, '.tsc-baseline.json')).toBe(tscBaseline([['src/b.ts', 'TS2322', msg, 1], ['src/b.ts', 'TS2322', other, 1]]));
  });

  it.each([
    ['no baseline file', {}, CONFIG],
    ['commands.typecheck.typescript null', { '.tsc-baseline.json': OLD_BASELINE }, 'commands:\n  typecheck:\n    typescript: null\n'],
  ])('%s: no alignment, the plain rename', (_label, extra, config) => {
    const root = tsProject({ 'src/a.ts': A, 'src/c.ts': C, ...extra }, config);
    const before = files(root);
    expect(renameOld(root, true)).toEqual({ code: 0, out: expectedOut([renameHeader('Old', 'New')], [{ path: 'src/a.ts', old: A, new: A_NEW }], true), err: '' });
    expect({ ...files(root), 'src/a.ts': A }).toEqual(before);
  });
});
